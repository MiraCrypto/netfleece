# Hello World!

netfleece is a small Microsoft .NET Remoting Binary Format (MS-NRBF) parser.
It is capable of reading in a binary stream and parsing it into a generic,
json-like structure.

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