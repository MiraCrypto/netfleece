#!/usr/bin/python3
"""
dnb implements a parser based on MS-NRBF, the .NET Binary Format data structure.
https://msdn.microsoft.com/en-us/library/cc236844.aspx

Very loosely based on https://github.com/agix/NetBinaryFormatterParser
"""

#import base64
import argparse
import decimal
from enum import Enum
import json
import os.path
import re
import sys
import struct
from functools import singledispatch
from functools import wraps

def valuedispatch(func):
    """
    valuedispatch function decorator, as obtained from
    http://lukasz.langa.pl/8/single-dispatch-generic-functions/
    """
    _func = singledispatch(func)

    @_func.register(Enum)
    def _enumvalue_dispatch(*args, **kw):
        enum, value = args[0], args[0].value
        if value not in _func.registry:
            return _func.dispatch(object)(*args, **kw)
        dispatch = _func.registry[value]
        _func.register(enum, dispatch)
        return dispatch(*args, **kw)

    @wraps(func)
    def wrapper(*args, **kw):
        if args[0] in _func.registry:
            return _func.registry[args[0]](*args, **kw)
        return _func(*args, **kw)

    def register(value):
        return lambda f: _func.register(value, f)

    wrapper.register = register
    wrapper.dispatch = _func.dispatch
    wrapper.registry = _func.registry
    return wrapper


def record_id(record):
    if 'ObjectId' in record:
        return record['ObjectId']
    if 'ClassInfo' in record:
        return record['ClassInfo']['ObjectId']
    if 'ArrayInfo' in record:
        return record['ArrayInfo']['ObjectId']
    return None

class Stream:
    def __init__(self, f):
        self.f = f

    def read(self, size):
        rdbytes = self.f.read(size)
        if len(rdbytes) != size:
            raise EOFError()
        return rdbytes

    def record(self):
        """Read an entire record from the stream."""
        rtype = self.RecordTypeEnumeration()
        obj = { 'RecordTypeEnum': rtype.name }
        obj.update(rtype.parse(self))
        return obj

    # 2.1.1 Common Data Types

    def boolean(self):
        return struct.unpack('<?', self.read(1))[0]

    def byte(self):
        return struct.unpack('<B', self.read(1))[0]

    def int8(self):
        return struct.unpack('<b', self.read(1))[0]

    def int16(self):
        return struct.unpack('<h', self.read(2))[0]

    def int32(self):
        return struct.unpack('<i', self.read(4))[0]

    def int64(self):
        return struct.unpack('<q', self.read(8))[0]

    def uint16(self):
        return struct.unpack('<H', self.read(2))[0]

    def uint32(self):
        return struct.unpack('<I', self.read(4))[0]

    def uint64(self):
        return struct.unpack('<Q', self.read(8))[0]

    # 2.1.1.1 Char
    def char(self):
        #FIXME: How many bytes do we read here?
        raise Exception('Not Implemented')

    # 2.1.1.2 Double
    def double(self):
        return struct.unpack('<d', self.read(8))[0]

    # 2.1.1.3 Single
    def single(self):
        return struct.unpack('<f', self.read(4))[0]

    # 2.1.1.4 TimeSpan
    def timespan(self):
        return self.int64()

    # 2.1.1.5 DateTime
    def datetime(self):
        ticks = self.int64()
        ret = {}
        if ticks & 0x01:
            ret['Kind'] = 'UTC'
        elif ticks & 0x02:
            ret['Kind'] = 'Local'
        else:
            ret['Kind'] = None
        ret['ticks'] = ticks & ~0x03
        return ret

    # 2.1.1.6 Length Prefixed String
    def string(self):
        length = 0
        shift = 0
        while True:
            # FIXME: Must not exceed six bytes read
            byte = self.byte()
            length += (byte & ~0x80) << shift
            shift += 7
            if not byte & 0x80:
                break
        raw = self.read(length)
        return raw.decode("utf-8")

    # 2.1.1.7 Decimcal
    def decimal(self):
        d = self.string()
        match = re.match(r"^(-)?([0-9]+)(\.([0-9]+))?$", d)
        if not match:
            raise Exception("Decimal in invalid format")
        return decimal.Decimal(d)

    # 2.1.1.8 ClassTypeInfo
    def ClassTypeInfo(self):
        return {
            'TypeName': self.string(),
            'LibraryId': self.int32()
        }

    # 2.1.2 Enumerations

    # 2.1.2.1 RecordTypeEnumeration
    def RecordTypeEnumeration(self):
        return RecordTypeEnum(self.byte())

    # 2.1.2.2 BinaryTypeEnumeration
    def BinaryTypeEnumeration(self):
        return BinaryTypeEnum(self.byte())

    # 2.1.2.3 PrimitiveTypeEnumeration
    def PrimitiveTypeEnumeration(self):
        return PrimitiveTypeEnum(self.byte())

    # 2.2 Method Invocation Records
    # 2.2.2 Common Structures

    # 2.2.2.1 ValueWithCode
    def ValueWithCode(self):
        enum = self.PrimitiveTypeEnumeration()
        val = enum.parse(self)
        return {
            'PrimitiveTypeEnum': enum.value,
            'Value': val
        }

    # 2.2.2.2 StringValueWithCode
    def StringValueWithCode(self):
        ret = self.ValueWithCode()
        assert ret['Value'] == PrimitiveTypeEnum.String.value

    # 2.2.2.3 ArrayOfValueWithCode
    def ArrayOfValueWithCode(self):
        length = self.int32()
        values = []
        for _ in range(length):
            values.append(self.ValueWithCode())
        return { "Length": length,
                 "ListOfValueWithCode": values }

    # 2.3: Class Records
    # 2.3.1: Common Structures

    # 2.3.1.1: ClassInfo
    def ClassInfo(self):
        cinfo = {
            'ObjectId': self.int32(),
            'Name': self.string(),
            'MemberCount': self.int32(),
            'MemberNames': []
        }
        for _ in range(cinfo['MemberCount']):
            cinfo['MemberNames'].append(self.string())
        return cinfo

    # 2.3.1.2: MemberTypeInfo
    def MemberTypeInfo(self, count):
        bnum = []
        bres = []
        aifo = []
        for _ in range(count):
            bnum.append(self.BinaryTypeEnumeration())
        for b in bnum:
            bres.append(b.name)
            info = b.parse_info(self)
            aifo.append(info)
        return {
            'BinaryTypeEnums': bres,
            'AdditionalInfos': aifo
        }

    # 2.4 Array Records
    # 2.4.1 Enumerations

    # 2.4.1.1 BinaryArrayTypeEnumeration
    def BinaryArrayTypeEnumeration(self):
        return BinaryArrayTypeEnum(self.byte())


class PrimitiveTypeEnum(Enum):
    Boolean  = 1
    Byte     = 2
    Char     = 3
    # 4
    Decimal  = 5
    Double   = 6
    Int16    = 7
    Int32    = 8
    Int64    = 9
    SByte    = 10
    Single   = 11
    TimeSpan = 12
    DateTime = 13
    UInt16   = 14
    UInt32   = 15
    UInt64   = 16
    Null     = 17
    String   = 18

    @valuedispatch
    def parse(self, f):
        raise Exception("Unimplemented PrimitiveTypeEnum.parse(%s:%d)" % (self.name, self.value))

    @parse.register(Boolean)
    def _parse_boolean(self, f):
        return f.boolean()

    @parse.register(Byte)
    def _parse_byte(self, f):
        return f.byte()

    @parse.register(Char)
    def _parse_char(self, f):
        return f.char()

    @parse.register(Decimal)
    def _parse_decimal(self, f):
        return f.decimal()

    @parse.register(Double)
    def _parse_double(self, f):
        return f.double()

    @parse.register(Int16)
    def _parse_int16(self, f):
        return f.int16()

    @parse.register(Int32)
    def _parse_int32(self, f):
        return f.i32()

    @parse.register(Int64)
    def _parse_int64(self, f):
        return f.int64()

    @parse.register(SByte)
    def _parse_sbyte(self, f):
        return f.int8()

    @parse.register(Single)
    def _parse_single(self, f):
        return f.single()

    @parse.register(TimeSpan)
    def _parse_timespan(self, f):
        return f.timespan()

    @parse.register(DateTime)
    def _parse_datetime(self, f):
        return f.datetime()

    @parse.register(UInt16)
    def _parse_uint16(self, f):
        return f.uint16()

    @parse.register(UInt32)
    def _parse_uint32(self, f):
        return f.uint32()

    @parse.register(UInt64)
    def _parse_uint64(self, f):
        return f.uint64()

    @parse.register(Null)
    def _parse_null(self, f):
        return None

    @parse.register(String)
    def _parse_string(self, f):
        return f.string()


class BinaryTypeEnum(Enum):
    """
    Enumeration representing a BinaryTypeEnumeration.
    Present in MemberTypeInfo and BinaryArray structures.
    """
    Primitive      = 0
    String         = 1
    Object         = 2
    SystemClass    = 3
    Class          = 4
    ObjectArray    = 5
    StringArray    = 6
    PrimitiveArray = 7

    # AdditionalInfo dispatch

    @valuedispatch
    def parse_info(self, f):
        '''Parses AdditionalInfo correlating to the given BinaryTypeEnum.'''
        raise Exception("Unimplemented BinaryTypeEnum.parse_info(%s:%d)" % (self.name, self.value))

    @parse_info.register(Primitive)
    def _parse_info_primitive(self, f):
        return f.PrimitiveTypeEnumeration().name

    @parse_info.register(String)
    def _parse_info_string(self, f):
        return None

    @parse_info.register(Object)
    def _parse_info_object(self, f):
        return None

    @parse_info.register(SystemClass)
    def _parse_info_systemclass(self, f):
        return f.String()

    @parse_info.register(Class)
    def _parse_info_class(self, f):
        return f.ClassTypeInfo()

    @parse_info.register(ObjectArray)
    def _parse_info_objectarray(self, f):
        return None

    @parse_info.register(StringArray)
    def _parse_info_stringarray(self, f):
        return None

    @parse_info.register(PrimitiveArray)
    def _parse_info_primitivearray(self, f):
        return f.PrimitiveTypeEnumeration().name

    # Value parse dispatch

    @valuedispatch
    def parse(self, f, info):
        raise Exception("Unimplemented BinaryTypeEnum.parse(%s:%d)" % (self.name, self.value))

    @parse.register(Primitive)
    def _parse_primitive(self, f, info):
        e = PrimitiveTypeEnum[info]
        return e.parse(f)

    @parse.register(String)
    def _parse_string(self, f, info):
        return f.record()

#    @parse.register(Object)
#    def _parse_object(self, f, info):

    @parse.register(SystemClass)
    def _parse_systemclass(self, f, info):
        return f.record()

    @parse.register(Class)
    def _parse_class(self, f, info):
        return f.record()

#    @parse.register(ObjectArray)
#    def _parse_objectarray(self, f, info):

#    @parse.register(StringArray)
#    def _parse_stringarray(self, f, info):

#    @parse.register(PrimitiveArray)
#    def _parse_primitivearray(self, f, info):


class BinaryArrayTypeEnum(Enum):
    Single            = 0
    Jagged            = 1
    Rectangular       = 2
    SingleOffset      = 3
    JaggedOffset      = 4
    RectangularOffset = 5

    def has_bounds(self):
        return True if ('Offset' in str(self.name)) else False


class RecordTypeEnum(Enum):
    SerializedStreamHeader         = 0
    ClassWithId                    = 1
    SystemClassWithMembers         = 2
    ClassWithMembers               = 3
    SystemClassWithMembersAndTypes = 4
    ClassWithMembersAndTypes       = 5
    BinaryObjectString             = 6
    BinaryArray                    = 7
    MemberPrimitiveTyped           = 8
    MemberReference                = 9
    ObjectNull                     = 10
    MessageEnd                     = 11
    BinaryLibrary                  = 12
    ObjectNullMultiple256          = 13
    ObjectNullMultiple             = 14
    ArraySinglePrimitive           = 15
    ArraySingleObject              = 16
    ArraySingleString              = 17
    # 18
    # 19
    ArrayOfType                    = 20
    MethodCall                     = 21
    MethodReturn                   = 22

    def __val_common(self, f, classRecord):
        values = []
        for i in range(classRecord['ClassInfo']['MemberCount']):
            bte = classRecord['MemberTypeInfo']['BinaryTypeEnums'][i]
            b = BinaryTypeEnum[bte]
            values.append(b.parse(f, classRecord['MemberTypeInfo']['AdditionalInfos'][i]))
        return values

    def __class_common(self, f, objid, record, reference = None):
        # Reference is an external ClassID Reference, if any
        if not reference:
            reference = record
        values = self.__val_common(f, reference)
        dnb._registerObject(objid, record, values)
        record['Values'] = values
        return record

    @valuedispatch
    def parse(self, f):
        raise Exception("Unimplemented RecordTypeEnum.parse(%s:%d)" % (self.name, self.value))

    @parse.register(SerializedStreamHeader)
    def _parse_00(self, f):
        return {
            'RootId': f.int32(),
            'HeaderId': f.int32(),
            'MajorVersion': f.int32(),
            'MinorVersion': f.int32()
        }

    @parse.register(ClassWithId)
    def _parse_01(self, f):
        record = {
            'ObjectId': f.int32(),
            'MetadataId': f.int32()
        }
        fetch = dnb._fetchObject(record['MetadataId'])
        if dnb._expand:
            record.update(fetch)
        return self.__class_common(f, record['ObjectId'], record, fetch)

    @parse.register(SystemClassWithMembers)
    def _parse_02(self, f):
        record = {
            'ClassInfo': f.ClassInfo()
        }
        dnb._registerObject(record['ClassInfo']['ObjectId'], record)
        return record

    @parse.register(ClassWithMembers)
    def _parse_03(self, f):
        record = {
            'ClassInfo': f.ClassInfo(),
            'LibraryId': f.int32()         # REFERENCE to a BinaryLibrary record
        }
        dnb._registerObject(record['ClassInfo']['ObjectId'], record)
        return record

    def __mat_common(self, f, system):
        classinfo = f.ClassInfo()
        mtypeinfo = f.MemberTypeInfo(classinfo['MemberCount'])
        if not system:
            libraryid = f.int32()
        record = {
            'ClassInfo': classinfo,
            'MemberTypeInfo': mtypeinfo
        }
        if not system:
            record['LibraryId'] = libraryid
        return self.__class_common(f, record['ClassInfo']['ObjectId'], record)

    @parse.register(SystemClassWithMembersAndTypes)
    def _parse_04(self, f):
        return self.__mat_common(f, True)

    @parse.register(ClassWithMembersAndTypes)
    def _parse_05(self, f):
        return self.__mat_common(f, False)

    @parse.register(BinaryObjectString)
    def _parse_06(self, f):
        record = {
            'ObjectId': f.int32(),
            'Value': f.string()
        }
        dnb._registerObject(record['ObjectId'], record, record['Value'])
        return record

    @parse.register(BinaryArray)
    def _parse_07(self, f):
        objectid = f.int32()
        binaryArrayType = f.BinaryArrayTypeEnumeration()
        rank = f.int32()
        lengths = []
        for i in range(rank):
            lengths.append(f.int32())
        bounds = []
        if binaryArrayType.has_bounds():
            for i in range(rank):
                bounds.append(f.int32())
        binarytype = f.BinaryTypeEnumeration()
        atypeinfo = binarytype.parse_info(f)
        record = {
            'ObjectId': objectid,
            'BinaryArrayTypeEnum': binaryArrayType.name,
            'rank': rank,
            'Lengths': lengths,
            'LowerBounds': bounds,
            'TypeEnum': binarytype.name,
            'AdditionalTypeInfo': atypeinfo
        }

        # FIXME FIXME
        if not binaryArrayType.name == 'Single':
            raise Exception('BinaryArray of type %s is not implemented' % binaryArrayType.name)

        # Total Cells
        l = 1
        for i in range(rank):
            l = l * record['Lengths'][i]

        # bweoop
        values = []
        i = 0
        while i < l:
            r = binarytype.parse(f, atypeinfo)
            if isinstance(r, dict):
                if 'NullCount' in r:
                    # Should handle both ObjectNullMultiple and ObjectNullMultiple256
                    i += r['NullCount']
                else:
                    i += 1
                if i > l:
                    raise Exception('Too many NullMultiple records?')
                values.append(r)

        dnb._registerObject(record['ObjectId'], record, values)
        record['Values'] = values
        return record

    @parse.register(MemberReference)
    def _parse_09(self, f):
        record = {
            'IdRef': f.int32()
        }
        dnb._registerReference(record['IdRef'], record)
        return record

    @parse.register(ObjectNull)
    def _parse_10(self, f):
        return { }

    @parse.register(MessageEnd)
    def _parse_11(self, f):
        return { }

    @parse.register(BinaryLibrary)
    def _parse_12(self, f):
        return {
            'LibraryId': f.int32(),
            'LibraryName': f.String()
        }

    @parse.register(ObjectNullMultiple256)
    def _parse_13(self, f):
        return {
            'NullCount': f.byte()
        }

    @parse.register(ObjectNullMultiple)
    def _parse_14(self, f):
        return {
            'NullCount': f.int32()
        }


class DNBinary:
    def __init__(self, f, best_effort=False, expand=False):
        self.f = Stream(f)
        self._objects = {}
        self._objrefs = []
        self._values = {}
        self._pruned = set()
        self._records = []
        self._strict = not best_effort
        self._expand = expand

    def _registerObject(self, ref, obj, values=None):
        self._objects[ref] = dict(obj)
        self._values[ref] = values

    def _fetchObject(self, ref):
        return self._objects[ref]

    def _fetchValues(self, ref):
        if ref in self._values:
            return self._values[ref]

    def _registerReference(self, ref, obj):
        self._objrefs.append((ref, obj))

    def _crunchClass(self, value):
        if not isinstance(value, dict):
            raise Exception("Cannot crunch record as Class")
        classinfo = None
        if 'ClassInfo' in value:
            classinfo = value['ClassInfo']
        else:
            fetch = self._fetchObject(value['MetadataId'])
            classinfo = fetch['ClassInfo']
        kv = {}
        for i in range(classinfo['MemberCount']):
            name = classinfo['MemberNames'][i]
            v = self._crunch(value['Values'][i])
            if v is not None:
                kv[name] = v
        return kv

    def _crunch(self, value):
        """
        Given a JSON representation of a .NET Binary, return a recursively
        "minified" version of it, stripping away most of the metadata.
        """
        # If it's a dict...
        if isinstance(value, dict):
            # If it's a Class Record:
            if 'ClassInfo' in value or 'MetadataId' in value:
                return self._crunchClass(value)
            if 'RecordTypeEnum' in value:
                # If it's a very verbose NULL:
                if value['RecordTypeEnum'] == 'ObjectNull':
                    return None
            if 'Values' in value:
                # If it's an Array-type record:
                return self._crunch(value['Values'])
            if 'Value' in value:
                # If it's a primitive-type record:
                return self._crunch(value['Value'])
            # Hmm, what is this? Try our best:
            d = {}
            for (k,v) in value.items():
                v = self._crunch(v)
                if v is not None:
                    d[k] = v
            return d
        # Well, it might be a list, too:
        if isinstance(value, list):
            return [self._crunch(v) for v in value]
        # Failing all else, just return the thing.
        return value

    def parse(self):
        while True:
            try:
                record = self.f.record()
                self._records.append(record)
            except Exception as E:
                if self._strict:
                    raise
                print("Err, it exploded... [%s]" % str(E))
                break
            if record['RecordTypeEnum'] == 'MessageEnd':
                break
        return self._records

    def _find_record(self, rid):
        for i in range(len(self._records)):
            r = self._records[i]
            if record_id(r) == rid:
                return i

    def _prune(self, objid):
        if objid in self._pruned:
            return
        x = self._find_record(objid)
        if x:
            del self._records[x]
        self._pruned.add(objid)

    def backfill(self, prune = True):
        for refs in self._objrefs:
            objid = refs[0]
            refs[1].update(self._fetchObject(objid))
            values = self._fetchValues(objid)
            refs[1]['Values'] = values
            if prune:
                self._prune(objid)
        return self._records

    def crunch(self):
        rootID = self._records[0]['RootId']
        x = self._find_record(rootID)
        return self._crunch(self._records[x])


def main():
    parser = argparse.ArgumentParser(description='Convert json to dotnet binary formatter')
    parser.add_argument('-i', dest='inputFile', required=True)
    parser.add_argument('-o', dest='outputFile', required=False)
    #parser.add_argument('-e', dest='encode',
    #                    help='Url and base64 decode the input binary',
    #                    required=False, action='store_true')
    parser.add_argument('-x', dest='expand',
                        help='Expand records with referenced Class records',
                        required=False, action='store_true')
    parser.add_argument('-b', dest='backfill',
                        help='Backfill forward references',
                        required=False, action='store_true')
    parser.add_argument('-c', dest='crunch',
                        help='Crunch JSON into a minified form',
                        required=False, action='store_true')
    parser.add_argument('-v', dest='verbose', help='Verbose mode',
                        required=False, action='store_true')
    parser.add_argument('-p', dest='print', help='Print JSON',
                        required=False, action='store_true')
    parser.add_argument('-E', dest='lax',
                        help='Apply a best effort to dumping JSON when encountering errors',
                        required=False, action='store_true')
    args = parser.parse_args()

    verbose = args.verbose
    fr = open(args.inputFile, 'rb')
    dnb = DNBinary(fr, best_effort=args.lax, expand=args.expand)

    j = dnb.parse()
    if args.backfill:
        j = dnb.backfill()
    if args.crunch:
        j = dnb.crunch()

    if args.outputFile:
        with open(args.outputFile, 'w') as fw:
            fw.write(json.dumps(j))
    if args.print:
        print(json.dumps(j, indent=2))

    print("\n")
    print("%s: " % args.inputFile)
    print("\tTop level records: %d" % len(j))
    print("\tObject Definitions: %d" % len(dnb._objects))
    print("\tReferences: %d" % len(dnb._objrefs))

if __name__ == '__main__':
    main()
