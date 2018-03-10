#!/usr/bin/python3
import sys
import struct
import datetime
import json
import argparse
#import base64
import urllib

from enum import Enum
from functools import singledispatch
from functools import wraps

def valuedispatch(func):
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

    wrapper.register = _func.register
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

    # 2.1.1 Common Data Types

    def boolean(self):
        return struct.unpack('<?', self.read(1))[0]

    def u8(self):
        return struct.unpack('<B', self.read(1))[0]

    def i32(self):
        return struct.unpack('<I', self.read(4))[0]

    def i64(self):
        return struct.unpack('<q', self.read(8))[0]

    def f32(self):
        return struct.unpack('<f', self.read(4))[0]

    def f64(self):
        return struct.unpack('<d', self.read(8))[0]

    def u64(self):
        return struct.unpack('<Q', self.read(8))[0]

    # 2.1.1.1 Char
    def Char(self):
        raise Exception('Not Implemented')

    # 2.1.1.2 Double
    def Double(self):
        return self.f64()

    # 2.1.1.3 Single
    def Single(self):
        return self.f32()

    # 2.1.1.4 TimeSpan
    def TimeSpan(self):
        return self.i64()

    # 2.1.1.5 DateTime
    def DateTime(self):
        dt = self.i64()
        r = {}
        if (dt & 0x01):
            r['Kind'] = 'UTC'
        elif (dt & 0x02):
            r['Kind'] = 'Local'
        else:
            r['Kind'] = None
        r['ticks'] = dt & ~0x03
        return r

    # 2.1.1.6 Length Prefixed String
    def String(self):
        length = 0
        shift = 0
        while True:
            byte = self.u8()
            length += (byte & ~0x80) << shift
            shift += 7
            if not (byte & 0x80):
                break
        raw = self.read(length)
        return raw.decode("utf-8")

    # 2.1.1.7 Decimcal
    def Decimal(self):
        d = self.String()
        # Todo: verify string is in a correct format.
        return d

    # 2.1.1.8 ClassTypeInfo
    def ClassTypeInfo(self):
        return {
            'TypeName': self.String(),
            'LibraryId': self.i32()
        }

    # 2.1.2 Enumerations

    # 2.1.2.1 RecordTypeEnumeration
    def RecordTypeEnumeration(self):
        return RecordTypeEnum(self.u8())

    # 2.1.2.2 BinaryTypeEnumeration
    def BinaryTypeEnumeration(self):
        tmp = self.u8()
        return BinaryTypeEnum(tmp)

    # 2.1.2.3 PrimitiveTypeEnumeration
    def PrimitiveTypeEnumeration(self):
        return PrimitiveTypeEnum(self.u8())

    # 2.3: Class Records
    # 2.3.1: Common Structures

    # 2.3.1.1: ClassInfo
    def ClassInfo(self):
        cinfo = {
            'ObjectId': self.i32(),
            'Name': self.String(),
            'MemberCount': self.i32(),
            'MemberNames': []
        }
        for i in range(cinfo['MemberCount']):
            cinfo['MemberNames'].append(self.String())
        return cinfo

    # 2.3.1.2: MemberTypeInfo
    def MemberTypeInfo(self, count):
        bnum = []
        bres = []
        aifo = []
        for i in range(count):
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
        return BinaryArrayTypeEnum(self.u8())


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

    @parse.register(Int32)
    def _parse_int32(self, f):
        return f.i32()

    @parse.register(Single)
    def _parse_single(self, f):
        return f.Single()

    @parse.register(UInt64)
    def _parse_uint64(self, f):
        return f.u64()


class BinaryTypeEnum(Enum):
    """Enumeration representing a BinaryTypeEnumeration, present in MemberTypeInfo and BinaryArray structures."""
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
    def parse(self, dnb, info):
        raise Exception("Unimplemented BinaryTypeEnum.parse(%s:%d)" % (self.name, self.value))

    @parse.register(Primitive)
    def _parse_primitive(self, dnb, info):
        e = PrimitiveTypeEnum[info]
        return e.parse(dnb.f)

    @parse.register(String)
    def _parse_string(self, dnb, info):
        return dnb._parseRecord()

#    @parse.register(Object)
#    def _parse_object(self, dnb, info):

    @parse.register(SystemClass)
    def _parse_systemclass(self, dnb, info):
        return dnb._parseRecord()

    @parse.register(Class)
    def _parse_class(self, dnb, info):
        return dnb._parseRecord()

#    @parse.register(ObjectArray)
#    def _parse_objectarray(self, dnb, info):

#    @parse.register(StringArray)
#    def _parse_stringarray(self, dnb, info):

#    @parse.register(PrimitiveArray)
#    def _parse_primitivearray(self, dnb, info):


class BinaryArrayTypeEnum(Enum):
    Single            = 0
    Jagged            = 1
    Rectangular       = 2
    SingleOffset      = 3
    JaggedOffset      = 4
    RectangularOffset = 5

    def has_bounds(self):
        return True if ('Offset' in self.name) else False


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

    def __val_common(self, dnb, classRecord):
        values = []
        for i in range(classRecord['ClassInfo']['MemberCount']):
            bte = classRecord['MemberTypeInfo']['BinaryTypeEnums'][i]
            b = BinaryTypeEnum[bte]
            values.append(b.parse(dnb, classRecord['MemberTypeInfo']['AdditionalInfos'][i]))
        return values

    def __class_common(self, dnb, objid, record, reference = None):
        # Reference is an external ClassID Reference, if any
        if not reference:
            reference = record
        values = self.__val_common(dnb, reference)
        dnb._registerObject(objid, record, values)
        record['Values'] = values
        return record

    @valuedispatch
    def parse(self, dnb):
        raise Exception("Unimplemented RecordTypeEnum.parse(%s:%d)" % (self.name, self.value))

    @parse.register(SerializedStreamHeader)
    def _parse_00(self, dnb):
        return {
            'RootId': dnb.f.i32(),
            'HeaderId': dnb.f.i32(),
            'MajorVersion': dnb.f.i32(),
            'MinorVersion': dnb.f.i32()
        }

    @parse.register(ClassWithId)
    def _parse_01(self, dnb):
        record = {
            'ObjectId': dnb.f.i32(),
            'MetadataId': dnb.f.i32()
        }
        fetch = dnb._fetchObject(record['MetadataId'])
        if dnb._expand:
            record.update(fetch)
        return self.__class_common(dnb, record['ObjectId'], record, fetch)

    @parse.register(SystemClassWithMembers)
    def _parse_02(self, dnb):
        record = {
            'ClassInfo': dnb.f.ClassInfo()
        }
        dnb._registerObject(record['ClassInfo']['ObjectId'], record)
        return record

    @parse.register(ClassWithMembers)
    def _parse_03(self, dnb):
        record = {
            'ClassInfo': dnb.f.ClassInfo(),
            'LibraryId': dnb.f.i32()           # REFERENCE to a BinaryLibrary record
        }
        dnb._registerObject(record['ClassInfo']['ObjectId'], record)
        return record

    def __mat_common(self, dnb, system):
        classinfo = dnb.f.ClassInfo()
        mtypeinfo = dnb.f.MemberTypeInfo(classinfo['MemberCount'])
        if not system:
            libraryid = dnb.f.i32()
        record = {
            'ClassInfo': classinfo,
            'MemberTypeInfo': mtypeinfo
        }
        if not system:
            record['LibraryId'] = libraryid
        return self.__class_common(dnb, record['ClassInfo']['ObjectId'], record)

    @parse.register(SystemClassWithMembersAndTypes)
    def _parse_04(self, dnb):
        return self.__mat_common(dnb, True)

    @parse.register(ClassWithMembersAndTypes)
    def _parse_05(self, dnb):
        return self.__mat_common(dnb, False)

    @parse.register(BinaryObjectString)
    def _parse_06(self, dnb):
        record = {
            'ObjectId': dnb.f.i32(),
            'Value': dnb.f.String()
        }
        # Hmm, not "Values" though, eh?
        dnb._registerObject(record['ObjectId'], record, record['Value'])
        return record

    @parse.register(BinaryArray)
    def _parse_07(self, dnb):
        objectid = dnb.f.i32()
        binaryArrayType = dnb.f.BinaryArrayTypeEnumeration()
        rank = dnb.f.i32()
        lengths = []
        for i in range(rank):
            lengths.append(dnb.f.i32())
        bounds = []
        if binaryArrayType.has_bounds():
            for i in range(rank):
                bounds.append(dnb.f.i32())
        binarytype = dnb.f.BinaryTypeEnumeration()
        atypeinfo = binarytype.parse_info(dnb.f)
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
            r = binarytype.parse(dnb, atypeinfo)
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
    def _parse_09(self, dnb):
        record = {
            'IdRef': dnb.f.i32()
        }
        dnb._registerReference(record['IdRef'], record)
        return record

    @parse.register(ObjectNull)
    def _parse_10(self, dnb):
        return { }

    @parse.register(MessageEnd)
    def _parse_11(self, dnb):
        return { }

    @parse.register(BinaryLibrary)
    def _parse_12(self, dnb):
        return {
            'LibraryId': dnb.f.i32(),
            'LibraryName': dnb.f.String()
        }

    @parse.register(ObjectNullMultiple256)
    def _parse_13(self, dnb):
        return {
            'NullCount': dnb.f.u8()
        }

    @parse.register(ObjectNullMultiple)
    def _parse_14(self, dnb):
        return {
            'NullCount': dnb.f.i32()
        }


class DNBinary:
    _expand = False
    _crunch = False
    _strict = False
    _expand = False
    _strict = True

    _objects = None
    _objrefs = None
    _values = None

    def __init__(self, f, best_effort = False, expand = False):
        self.f = Stream(f)
        self._objects = {}
        self._objrefs = []
        self._values = {}
        self._records = []
        self._strict = not best_effort
        self._expand = expand

    def _registerObject(self, ref, obj, values = None):
        self._objects[ref] = dict(obj)
        self._values[ref] = values

    def _fetchObject(self, ref):
        return self._objects[ref]

    def _fetchValues(self, ref):
        if ref in self._values:
            return self._values[ref]

    def _registerReference(self, ref, obj):
        self._objrefs.append((ref, obj))

    def _parseRecord(self, register=False):
        '''Read a record from the stream, but don't record it as a top-level object.'''
        rtype = self.f.RecordTypeEnumeration()
        obj = rtype.parse(self)
        obj['RecordTypeEnum'] = rtype.name
        if register:
            self._records.append(obj)
        return obj


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
        '''Given a JSON representation of a .NET Binary, return a recursively "minified" version of it, stripping away most of the metadata.'''
        # If it's a dict...
        if isinstance(value, dict):
            # If it's a Class Record:
            if (('ClassInfo' in value) or
                ('MetadataId' in value)):
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

    def parseRecord(self):
        '''Read a top-level record from the stream.'''
        return self._parseRecord(register=True)

    def parse(self):
        while True:
            try:
                record = self.parseRecord()
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

    def backfill(self, prune = True):
        for refs in self._objrefs:
            objid = refs[0]
            refs[1].update(self._fetchObject(objid))
            values = self._fetchValues(objid)
            refs[1]['Values'] = values
            if prune:
                x = self._find_record(objid)
                if x:
                    del self._records[x]
        return self._records

    def crunch(self):
        rootID = self._records[0]['RootId']
        x = self._find_record(rootID)
        return self._crunch(self._records[x])


def main():
    parser = argparse.ArgumentParser(description='Convert json to dotnet binary formatter')
    parser.add_argument('-i', dest='inputFile', required=True)
    parser.add_argument('-o', dest='outputFile', required=False)
    #parser.add_argument('-e', dest='encode', help='Url and base64 decode the input binary', required=False, action='store_true')
    parser.add_argument('-x', dest='expand', help='Expand records with referenced Class records', required=False, action='store_true')
    parser.add_argument('-b', dest='backfill', help='Backfill forward references', required=False, action='store_true')
    parser.add_argument('-c', dest='crunch', help='Crunch JSON into a minified form', required=False, action='store_true')
    parser.add_argument('-v', dest='verbose', help='Verbose mode', required=False, action='store_true')
    parser.add_argument('-p', dest='print', help='Print JSON', required=False, action='store_true')
    parser.add_argument('-E', dest='lax',
                        help='E for effort! Apply a best effort to dumping JSON when encountering errors',
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

if __name__=='__main__':
    main()
