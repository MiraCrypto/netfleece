# Hello World!

netfleece is a small Microsoft .NET Remoting Binary Format (MS-NRBF) parser.
It is capable of reading in a binary stream and parsing it into a generic,
json-serializable Python-native data structure.

# Why?

Distributed .NET projects sometimes use MS-NRBF streams for
serializing and deserializing data. netfleece allows you to
investigate that data in a convenient format that's widely supported
by a number of tools.

# Notable Missing Features:

* Not every record type is currently supported. If you find examples
  of files that utilize these records, please let me know and I will
  amend the tool.

* Arrays except for single dimensional, non-offset
  arrays are unimplemented.

# Acknowledgement

This is very loosely based on
https://github.com/agix/NetBinaryFormatterParser, which is a Python2
project, but also features a formatter that can perform the reverse
operation.

# Changelog

## v0.1.3.1
 - Fix empty PyPI package. Oops.

## v0.1.3

### Misc:
 - Switch to setuptools & setup.cfg
 - Use a module-level logger instead of a root-level one
 - Ensure all 'make check' tests pass.

## v0.1.2

### New:
- Preliminary support for single-dimension Jagged/Rectangular Arrays
- Expose parse() and iterparse() helpers, joining parseloop().

### Bugs:
- Fix 2.1.1.1 Char parsing
- Fix 2.1.1.6 LengthPrefixedString error conditions
- Fix 2.2.2.2 StringValueWithCode asserting erroneously
- Fix 2.4.3.2 ArraySingleObject not registering ObjectId
- Fix 2.4.3.3 ArraySinglePrimitive
- Fix 2.4.3.4 ArraySingleString not registering ObjectId

## v0.1.1 (2019-12-21)

- add streamable b64 support
- add parseloop to the public API
- refactored module naming structure

## v0.1.0 (2019-05-16)

- Initial release
