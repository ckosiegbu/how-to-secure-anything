"""PrismToken Thrift service -- ports libshlsm/modules/prismtoken1/TokenApi.

The Thrift TokenApi surface (handler.TokenApiHandler) sits on top of the SmBase
security-module abstraction (sts_sm). Transport binding is provided by
thrift_server (thriftpy2); the handler itself is transport-agnostic and is what
the test-suite drives directly.
"""
