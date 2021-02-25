#!/usr/bin/env python3
"""
netfleece implements a parser based on MS-NRBF, the .NET Remoting Binary Format.
https://msdn.microsoft.com/en-us/library/cc236844.aspx
"""

import argparse
import decimal
import json
import logging
import os.path
import re
import struct
from collections import namedtuple
from enum import Enum
from functools import singledispatch, wraps
from typing import BinaryIO

from . import b64stream


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


class PrimitiveStream:
    # pylint: disable=too-many-public-methods
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
        data = []
        data.append(self.byte())
        if data[0] & 0x80 == 0x00:
            # 0xxx xxxx
            length = 1
        elif data[0] & 0xE0 == 0xC0:
            # 110x xxxx
            length = 2
        elif data[0] & 0xF0 == 0xE0:
            # 1110 xxxx
            length = 3
        elif data[0] & 0xF8 == 0xF0:
            # 1111 0xxx
            length = 4
        else:
            raise Exception("Invalid UTF8 byte sequence")
        for _ in range(length - 1):
            data.append(self.byte())
        return bytes(data).decode('utf-8')

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
        for i in range(5):
            byte = self.byte()
            length += (byte & ~0x80) << shift
            shift += 7
            if not byte & 0x80:
                break
            if i == 4:
                raise Exception(f"Variable Length ({length}) exceeds maximum size")
        raw = self.read(length)
        return raw.decode("utf-8")

    # 2.1.1.7 Decimal
    def decimal(self):
        decstr = self.string()
        match = re.match(r"^(-)?([0-9]+)(\.([0-9]+))?$", decstr)
        if not match:
            raise Exception("Decimal in invalid format")
        return decimal.Decimal(decstr)


class PrimitiveTypeEnum(Enum):
    # pylint: disable=bad-whitespace
    # pylint: disable=unused-argument
    # pylint: disable=no-self-use
    Boolean  = 1
    Byte     = 2
    Char     = 3
    # 4 (Not defined in standard)
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
    def parse(self, _):
        raise Exception("Unimplemented PrimitiveTypeEnum.parse(%s)" %
                        repr(self))

    @parse.register(Boolean)
    def _parse_boolean(self, stream: PrimitiveStream):
        return stream.boolean()

    @parse.register(Byte)
    def _parse_byte(self, stream: PrimitiveStream):
        return stream.byte()

    @parse.register(Char)
    def _parse_char(self, stream: PrimitiveStream):
        return stream.char()

    @parse.register(Decimal)
    def _parse_decimal(self, stream: PrimitiveStream):
        return stream.decimal()

    @parse.register(Double)
    def _parse_double(self, stream: PrimitiveStream):
        return stream.double()

    @parse.register(Int16)
    def _parse_int16(self, stream: PrimitiveStream):
        return stream.int16()

    @parse.register(Int32)
    def _parse_int32(self, stream: PrimitiveStream):
        return stream.int32()

    @parse.register(Int64)
    def _parse_int64(self, stream: PrimitiveStream):
        return stream.int64()

    @parse.register(SByte)
    def _parse_sbyte(self, stream: PrimitiveStream):
        return stream.int8()

    @parse.register(Single)
    def _parse_single(self, stream: PrimitiveStream):
        return stream.single()

    @parse.register(TimeSpan)
    def _parse_timespan(self, stream: PrimitiveStream):
        return stream.timespan()

    @parse.register(DateTime)
    def _parse_datetime(self, stream: PrimitiveStream):
        return stream.datetime()

    @parse.register(UInt16)
    def _parse_uint16(self, stream: PrimitiveStream):
        return stream.uint16()

    @parse.register(UInt32)
    def _parse_uint32(self, stream: PrimitiveStream):
        return stream.uint32()

    @parse.register(UInt64)
    def _parse_uint64(self, stream: PrimitiveStream):
        return stream.uint64()

    @parse.register(Null)
    def _parse_null(self, stream: PrimitiveStream):
        return None

    @parse.register(String)
    def _parse_string(self, stream: PrimitiveStream):
        return stream.string()


class NetStream(PrimitiveStream):
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
        assert ret['PrimitiveTypeEnum'] == PrimitiveTypeEnum.String.value
        return ret

    # 2.2.2.3 ArrayOfValueWithCode
    def ArrayOfValueWithCode(self):
        length = self.int32()
        values = []
        for _ in range(length):
            values.append(self.ValueWithCode())
        return {"Length": length,
                "ListOfValueWithCode": values}

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
        btypes = []
        bnames = []
        additional_infos = []
        for _ in range(count):
            btypes.append(self.BinaryTypeEnumeration())
        for btype in btypes:
            bnames.append(btype.name)
            info = btype.parse_info(self)
            additional_infos.append(info)
        return {
            'BinaryTypeEnums': bnames,
            'AdditionalInfos': additional_infos
        }

    # 2.4 Array Records
    # 2.4.1 Enumerations
    # 2.4.1.1 BinaryArrayTypeEnumeration
    def BinaryArrayTypeEnumeration(self):
        return BinaryArrayTypeEnum(self.byte())

    # 2.4.2 Common Definitions
    # 2.4.2.1 ArrayInfo
    def ArrayInfo(self):
        return {
            'ObjectId': self.int32(),
            'Length': self.int32()
        }


ObjectReference = namedtuple('ObjectReference', ('refid', 'object'))


class RecordStream(NetStream):
    def __init__(self, stream, expand=False):
        super().__init__(stream)
        self._objects = {}
        self._objrefs = []
        self.expand = expand

    def record(self):
        """Read an entire record from the stream."""
        rtype = self.RecordTypeEnumeration()
        logging.debug("RecordTypeEnum: %s", rtype.name)
        obj = rtype.parse(self)
        obj['RecordTypeEnum'] = rtype.name
        return obj

    def get_object(self, ref):
        """Retrieve an object by its Object Reference."""
        return self._objects[ref]

    def get_metadata(self, ref):
        """Retrieve an object's metadata by its Object Reference."""
        meta = dict(self._objects[ref])
        if 'Value' in meta:
            del meta['Value']
        if 'Values' in meta:
            del meta['Values']
        return meta

    def set_object(self, ref, obj):
        """
        Register an object.

        Given an object reference, an object, and optionally its values,
        register this object so that it can be retrieved by later
        references to it.
        """
        self._objects[ref] = obj

    def register_reference(self, ref, obj):
        self._objrefs.append(ObjectReference(ref, obj))

    def backfill(self):
        """
        backfill expands object references.

        Replace any object references encountered by a pointer to the referenced
        object. Note that this is NOT a copy of the object.
        """
        for reference in self._objrefs:
            logging.debug("Reference to objid %s", str(reference.refid))
            obj = reference.object
            obj.update(self.get_object(reference.refid))

    @property
    def object_definitions(self):
        return len(self._objects)

    @property
    def object_references(self):
        return len(self._objrefs)


class BinaryTypeEnum(Enum):
    """
    Enumeration representing a BinaryTypeEnumeration.
    Present in MemberTypeInfo and BinaryArray structures.
    """
    # pylint: disable=bad-whitespace
    # pylint: disable=unused-argument
    # pylint: disable=no-self-use
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
    def parse_info(self, netf: NetStream):
        '''Parses AdditionalInfo correlating to the given BinaryTypeEnum.'''
        return None

    @parse_info.register(Primitive)
    def _parse_info_primitive(self, netf: NetStream):
        return netf.PrimitiveTypeEnumeration().name

    @parse_info.register(SystemClass)
    def _parse_info_systemclass(self, netf: NetStream):
        return netf.string()

    @parse_info.register(Class)
    def _parse_info_class(self, netf: NetStream):
        return netf.ClassTypeInfo()

    @parse_info.register(PrimitiveArray)
    def _parse_info_primitivearray(self, netf: NetStream):
        return netf.PrimitiveTypeEnumeration().name

    # Value parse dispatch

    @valuedispatch
    def parse(self, recf: RecordStream, info):
        # Everything except Primitives is stored as a full record;
        # See 2.7 for the BinaryRecordGrammar, and
        # See 2.5 for the MemberReference types.
        #
        # The mappings between BinaryTypeEnum and the actual record type
        # we expect to see here are not particularly clear; but the
        # grammar production rules indicate that everything except
        # MemberPrimitiveUnTyped is a full record, so we can parse them
        # as such.
        return recf.record()

    @parse.register(Primitive)
    def _parse_primitive(self, streamf: PrimitiveStream, info):
        # BTE's Primitive type has data serialized as a Primitive.
        enum = PrimitiveTypeEnum[info]
        return enum.parse(streamf)


class BinaryArrayTypeEnum(Enum):
    # pylint: disable=bad-whitespace
    Single            = 0
    Jagged            = 1
    Rectangular       = 2
    SingleOffset      = 3
    JaggedOffset      = 4
    RectangularOffset = 5

    def has_bounds(self):
        return 'Offset' in str(self.name)


class RecordTypeEnum(Enum):
    # pylint: disable=bad-whitespace
    # pylint: disable=unused-argument
    # pylint: disable=no-self-use
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
    # 18 (Not defined in standard)
    # 19 (Not defined in standard)
    # 20 (Not defined in standard)
    MethodCall                     = 21
    MethodReturn                   = 22

    def _parse_values(self, recf: RecordStream, class_record):
        values = []
        for i in range(class_record['ClassInfo']['MemberCount']):
            mti = class_record['MemberTypeInfo']
            bte = mti['BinaryTypeEnums'][i]
            btype = BinaryTypeEnum[bte]
            value = btype.parse(recf, mti['AdditionalInfos'][i])
            values.append(value)
        return values

    def _parse_class(self, recf: RecordStream, objid, record, reference=None):
        # Reference is an external ClassID Reference, if any
        if not reference:
            reference = record
        values = self._parse_values(recf, reference)
        record['Values'] = values
        recf.set_object(objid, record)
        return record

    @valuedispatch
    def parse(self, recf: RecordStream):
        raise Exception("Unimplemented RecordTypeEnum.parse(%s:%d)" % (
            self.name, self.value))

    @parse.register(SerializedStreamHeader)
    def _parse_00(self, streamf: PrimitiveStream):
        return {
            'RootId': streamf.int32(),
            'HeaderId': streamf.int32(),
            'MajorVersion': streamf.int32(),
            'MinorVersion': streamf.int32()
        }

    @parse.register(ClassWithId)
    def _parse_01(self, recf: RecordStream):
        record = {
            'ObjectId': recf.int32(),
            'MetadataId': recf.int32()
        }
        fetch = recf.get_metadata(record['MetadataId'])
        if recf.expand:
            record.update(fetch)
        return self._parse_class(recf, record['ObjectId'], record, fetch)

    @parse.register(SystemClassWithMembers)
    def _parse_02(self, recf: RecordStream):
        record = {
            'ClassInfo': recf.ClassInfo()
        }
        recf.set_object(record['ClassInfo']['ObjectId'], record)
        return record

    @parse.register(ClassWithMembers)
    def _parse_03(self, recf: RecordStream):
        record = {
            'ClassInfo': recf.ClassInfo(),
            'LibraryId': recf.int32()     # REFERENCE to a BinaryLibrary record
        }
        recf.set_object(record['ClassInfo']['ObjectId'], record)
        return record

    def _parse_members_and_types(self, recf: RecordStream, system: bool):
        classinfo = recf.ClassInfo()
        mtypeinfo = recf.MemberTypeInfo(classinfo['MemberCount'])
        if not system:
            libraryid = recf.int32()
        record = {
            'ClassInfo': classinfo,
            'MemberTypeInfo': mtypeinfo
        }
        if not system:
            record['LibraryId'] = libraryid
        return self._parse_class(recf, record['ClassInfo']['ObjectId'], record)

    @parse.register(SystemClassWithMembersAndTypes)
    def _parse_04(self, recf: RecordStream):
        return self._parse_members_and_types(recf, system=True)

    @parse.register(ClassWithMembersAndTypes)
    def _parse_05(self, recf: RecordStream):
        return self._parse_members_and_types(recf, system=False)

    @parse.register(BinaryObjectString)
    def _parse_06(self, recf: RecordStream):
        record = {
            'ObjectId': recf.int32(),
            'Value': recf.string()
        }
        recf.set_object(record['ObjectId'], record)
        return record

    @parse.register(BinaryArray)
    def _parse_07(self, recf: RecordStream):
        objectid = recf.int32()
        binary_array_type = recf.BinaryArrayTypeEnumeration()
        rank = recf.int32()
        lengths = []
        for i in range(rank):
            lengths.append(recf.int32())
        bounds = []
        if binary_array_type.has_bounds():
            for i in range(rank):
                bounds.append(recf.int32())
        binarytype = recf.BinaryTypeEnumeration()
        atypeinfo = binarytype.parse_info(recf)
        array_record = {
            'ObjectId': objectid,
            'BinaryArrayTypeEnum': binary_array_type.name,
            'rank': rank,
            'Lengths': lengths,
            'LowerBounds': bounds,
            'TypeEnum': binarytype.name,
            'AdditionalTypeInfo': atypeinfo
        }

        # TODO Implement arrays beyond the 'Single' type
        if binary_array_type.has_bounds():
            raise Exception("BinaryArray of type {} is not implemented".format(
                binary_array_type.name))

        if rank > 1:
            raise Exception(f"BinaryArray with Rank={rank} is not implemented")

        # Single, Jagged, Rectangular can progress, but only if rank=1.

        # Total Cells
        cells = 1
        for i in range(rank):
            cells = cells * array_record['Lengths'][i]

        # bweoop
        values = []
        i = 0
        while i < cells:
            record = binarytype.parse(recf, atypeinfo)
            if isinstance(record, dict):
                if 'NullCount' in record:
                    # Should handle both ObjectNullMultiple and ObjectNullMultiple256
                    i += record['NullCount']
                else:
                    i += 1
                if i > cells:
                    raise Exception('Too many NullMultiple records?')
            values.append(record)

        array_record['Values'] = values
        recf.set_object(array_record['ObjectId'], array_record)
        return array_record

    @parse.register(MemberPrimitiveTyped)
    def _parse_08(self, netf: NetStream):
        pte = netf.PrimitiveTypeEnumeration()
        record = {
            'PrimitiveTypeEnum': pte.name,
            'Value': pte.parse(netf)
        }
        return record

    @parse.register(MemberReference)
    def _parse_09(self, recf: RecordStream):
        record = {
            'IdRef': recf.int32()
        }
        recf.register_reference(record['IdRef'], record)
        return record

    @parse.register(ObjectNull)
    def _parse_10(self, streamf: PrimitiveStream):
        return {}

    @parse.register(MessageEnd)
    def _parse_11(self, streamf: PrimitiveStream):
        return {}

    @parse.register(BinaryLibrary)
    def _parse_12(self, streamf: PrimitiveStream):
        return {
            'LibraryId': streamf.int32(),
            'LibraryName': streamf.string()
        }

    @parse.register(ObjectNullMultiple256)
    def _parse_13(self, streamf: PrimitiveStream):
        return {
            'NullCount': streamf.byte()
        }

    @parse.register(ObjectNullMultiple)
    def _parse_14(self, streamf: PrimitiveStream):
        return {
            'NullCount': streamf.int32()
        }

    @staticmethod
    def _array_values(recf: RecordStream, length):
        values = []
        i = 0
        while i < length:
            value = recf.record()
            if isinstance(value, dict) and 'NullCount' in value:
                i += value['NullCount']
            else:
                i += 1
            if i > length:
                raise Exception('Too many NullMultiple records; exceeded array length')
            values.append(value)
        return values

    @parse.register(ArraySinglePrimitive)
    def _parse_15(self, recf: RecordStream):
        # (ArraySinglePrimitive *(MemberPrimitiveUnTyped))
        ainfo = recf.ArrayInfo()
        pte = recf.PrimitiveTypeEnumeration()
        values = [pte.parse(recf) for _ in range(ainfo['Length'])]
        obj = {
            'ArrayInfo': ainfo,
            'PrimitiveTypeEnum': pte.name,
            'Values': values
        }
        recf.set_object(ainfo['ObjectId'], obj)
        return obj

    @parse.register(ArraySingleObject)
    def _parse_16(self, recf: RecordStream):
        # (ArraySingleObject *(memberReference))
        #
        # Technically this grammar allows for MemberPrimitiveUnTyped,
        # but I think that's impossible to parse without type info, so
        # I am assuming that possibility is excluded.
        ainfo = recf.ArrayInfo()
        obj = {
            'ArrayInfo': ainfo,
            'Values': self._array_values(recf, ainfo['Length'])
        }
        recf.set_object(ainfo['ObjectId'], obj)
        return obj

    @parse.register(ArraySingleString)
    def _parse_17(self, recf: RecordStream):
        # (ArraySingleString *(BinaryObjectString/MemberReference/nullObject))
        # All of the above are full Record-types.
        ainfo = recf.ArrayInfo()
        obj = {
            'ArrayInfo': ainfo,
            'Values': self._array_values(recf, ainfo['Length'])
        }
        recf.set_object(ainfo['ObjectId'], obj)
        return obj

    # TODO: Implement _parse_{21, 22}


class DNBinary:
    def __init__(self, stream, expand=False):
        self.f = RecordStream(stream, expand=expand)
        self._records = []

    def _crunch_class(self, value):
        if not isinstance(value, dict):
            raise Exception("Cannot crunch this record as a Class")

        # If the user didn't expand ClassInfo metadata, we have to do it now:
        classinfo = None
        if 'ClassInfo' in value:
            classinfo = value['ClassInfo']
        else:
            fetch = self.f.get_metadata(value['MetadataId'])
            classinfo = fetch['ClassInfo']

        classobj = {}
        for i in range(classinfo['MemberCount']):
            name = classinfo['MemberNames'][i]
            v = self._crunch(value['Values'][i])
            if v is not None:
                classobj[name] = v
        return classobj

    def _crunch(self, value):
        """
        Returns a minified JSON representation of a .NET binary.

        Given a full JSON representation of a deserialized .NET binary,
        return a recursively minified version of it that strips away most
        of the .NET serialization metadata that is present in the structure.
        """
        ret = value
        # If it's a dict...
        if isinstance(value, dict):
            # If it's a Class Record:
            if 'ClassInfo' in value or 'MetadataId' in value:
                ret = self._crunch_class(value)
            elif value.get('RecordTypeEnum') == 'ObjectNull':
                # Null-type object
                ret = None
            elif 'Values' in value:
                # Array-type object
                ret = self._crunch(value['Values'])
            elif 'Value' in value:
                # Primitive-type record:
                ret = self._crunch(value['Value'])
            else:
                # Generic dict? Fallback:
                obj = {}
                for k, v in value.items():
                    v = self._crunch(v)
                    if v is not None:
                        obj[k] = v
                ret = obj
        elif isinstance(value, list):
            # List-type object:
            if isinstance(value, list):
                ret = [self._crunch(v) for v in value]
        return ret

    def _find_record_id(self, rid):
        for i in range(len(self._records)):
            record = self._records[i]
            if record_id(record) == rid:
                return i
        return None

    def _find_record(self, rid):
        for record in self._records:
            if record_id(record) == rid:
                return record
        return None

    def root(self):
        root_id = self._records[0]['RootId']
        return self._find_record(root_id)

    def backfill(self):
        self.f.backfill()
        return self.root()

    def crunch(self):
        return self._crunch(self.root())

    def parse(self):
        while True:
            record = self.f.record()
            self._records.append(record)
            if record['RecordTypeEnum'] == 'MessageEnd':
                break
        return self._records

    @property
    def object_definitions(self):
        return self.f.object_definitions

    @property
    def object_references(self):
        return self.f.object_references


def parse(handle: BinaryIO, decode: bool = False, expand: bool = False,
          backfill: bool = False, crunch: bool = False, root: bool = False):
    # pylint: disable=too-many-arguments
    """
    Parse a given binary MS-NRBF stream into a JSON-like data representation.

    :param decode: Apply a base64 decode to the incoming stream.
    :param expand: Expand references to Class Metadata to the full record.
    :param backfill: Expand back-references to the full record.
    :param crunch: Compact the JSON into a more minimal, native form.
    :param root: Return the root object only. (Implied by backfill and crunch.)
    """
    stream = b64stream.Base64Stream(handle) if decode else handle
    dnb = DNBinary(stream, expand=expand)

    jdata = dnb.parse()
    if backfill:
        jdata = dnb.backfill()
    if crunch:
        jdata = dnb.crunch()
    if root and not (backfill or crunch):
        # (backfill/crunch imply root, so no need.)
        jdata = dnb.root()

    logging.info("\tTop level records: %d", len(jdata))
    logging.info("\tObject Definitions: %d", dnb.object_definitions)
    logging.info("\tReferences: %d", dnb.object_references)

    return jdata


def iterparse(handle, decode=False, expand=False,
              backfill=False, crunch=False, root=False):
    # pylint: disable=too-many-arguments
    n = 1
    while handle.read(1):
        # As long as we have at least one byte, try to read an entire stream.
        handle.seek(-1, os.SEEK_CUR)

        logging.info("\nStream #%d", n)
        jdata = parse(handle, decode, expand, backfill, crunch, root)
        yield jdata
        n += 1


def parseloop(handle, decode=False, expand=False,
              backfill=False, crunch=False, root=False):
    # pylint: disable=too-many-arguments
    parsed = list(iterparse(handle, decode, expand, backfill, crunch, root))
    return parsed


def main():
    parser = argparse.ArgumentParser(description='Convert MSNRBF to json')
    parser.add_argument('-i', dest='inputFile', required=True)
    parser.add_argument('-o', dest='outputFile', required=False)
    parser.add_argument('-d', dest='decode',
                        help='base64 decode the input binary',
                        required=False, action='store_true')
    parser.add_argument('-x', dest='expand',
                        help='Expand records with referenced Class Metadata records',
                        required=False, action='store_true')
    parser.add_argument('-r', dest='root',
                        help='Return only the Root record',
                        required=False, action='store_true')
    parser.add_argument('-b', dest='backfill',
                        help='Backfill forward references (implies -r)',
                        required=False, action='store_true')
    parser.add_argument('-c', dest='crunch',
                        help='Crunch JSON into a minified form (implies -b, -r)',
                        required=False, action='store_true')
    parser.add_argument('-v', dest='verbose', help='Verbose mode',
                        required=False, action='store_true')
    parser.add_argument('-p', dest='print', help='Print JSON',
                        required=False, action='store_true')
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if args.crunch:
        args.backfill = True

    if args.backfill:
        args.root = True

    infile = open(args.inputFile, 'rb')
    logging.info("%s: ", args.inputFile)
    parsed = parseloop(infile, decode=args.decode, expand=args.expand,
                       backfill=args.backfill, crunch=args.crunch, root=args.root)

    if args.outputFile:
        with open(args.outputFile, 'w') as outf:
            outf.write(json.dumps(parsed))

    if args.print:
        print(json.dumps(parsed, indent=2))


if __name__ == '__main__':
    main()
