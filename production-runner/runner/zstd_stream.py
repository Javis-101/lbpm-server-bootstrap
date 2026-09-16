"""Small streaming adapter for the system libzstd ABI; no network or executable install."""
from __future__ import annotations
import ctypes as C
import ctypes.util
import io
import os

class In(C.Structure): _fields_=[('src',C.c_void_p),('size',C.c_size_t),('pos',C.c_size_t)]
class Out(C.Structure): _fields_=[('dst',C.c_void_p),('size',C.c_size_t),('pos',C.c_size_t)]


def library(path=''):
    path=path or os.environ.get('LBPM_RUNNER_LIBZSTD','') or ctypes.util.find_library('zstd')
    if not path: raise RuntimeError('LIBZSTD_NOT_FOUND: install/provide libzstd.so.1 via paths.libzstd; no automatic network install')
    lib=C.CDLL(path)
    funcs={'ZSTD_createCCtx':([],C.c_void_p),'ZSTD_createDCtx':([],C.c_void_p),
      'ZSTD_freeCCtx':([C.c_void_p],C.c_size_t),'ZSTD_freeDCtx':([C.c_void_p],C.c_size_t),
      'ZSTD_CCtx_setParameter':([C.c_void_p,C.c_int,C.c_int],C.c_size_t),
      'ZSTD_compressStream2':([C.c_void_p,C.POINTER(Out),C.POINTER(In),C.c_int],C.c_size_t),
      'ZSTD_decompressStream':([C.c_void_p,C.POINTER(Out),C.POINTER(In)],C.c_size_t),
      'ZSTD_isError':([C.c_size_t],C.c_uint),'ZSTD_getErrorName':([C.c_size_t],C.c_char_p),
      'ZSTD_versionNumber':([],C.c_uint)}
    for name,(args,res) in funcs.items():
        fn=getattr(lib,name); fn.argtypes=args; fn.restype=res
    if lib.ZSTD_versionNumber()<10400: raise RuntimeError('libzstd >=1.4 required')
    return lib


def check(lib,code):
    if lib.ZSTD_isError(code): raise IOError('zstd: '+lib.ZSTD_getErrorName(code).decode())
    return code


class Writer(io.RawIOBase):
    def __init__(self,stream,level=3,libpath=''):
        self.stream=stream; self.lib=library(libpath); self.ctx=self.lib.ZSTD_createCCtx(); self.finished=False
        if not self.ctx: raise MemoryError('ZSTD_createCCtx')
        check(self.lib,self.lib.ZSTD_CCtx_setParameter(self.ctx,100,level))
        check(self.lib,self.lib.ZSTD_CCtx_setParameter(self.ctx,201,1))  # checksumFlag
    def writable(self): return True
    def _pump(self,data,end):
        src=C.create_string_buffer(data); inp=In(C.cast(src,C.c_void_p),len(data),0)
        while True:
            buf=C.create_string_buffer(131072); out=Out(C.cast(buf,C.c_void_p),len(buf),0)
            left=check(self.lib,self.lib.ZSTD_compressStream2(self.ctx,C.byref(out),C.byref(inp),2 if end else 0))
            if out.pos: self.stream.write(buf.raw[:out.pos])
            if inp.pos==inp.size and (not end or left==0): break
    def write(self,b):
        if self.finished: raise ValueError('closed compressor')
        data=bytes(b); self._pump(data,False); return len(data)
    def finish(self):
        if not self.finished:
            self._pump(b'',True); self.finished=True; self.stream.flush()
    def close(self):
        if self.closed: return
        try: self.finish()
        finally:
            if self.ctx: self.lib.ZSTD_freeCCtx(self.ctx); self.ctx=None
            super().close()


class Reader(io.RawIOBase):
    def __init__(self,stream,libpath=''):
        self.stream=stream; self.lib=library(libpath); self.ctx=self.lib.ZSTD_createDCtx()
        if not self.ctx: raise MemoryError('ZSTD_createDCtx')
        self.data=b''; self.offset=0; self.expected=1; self.saw=False; self.eof=False
    def readable(self): return True
    def readinto(self,b):
        if self.eof: return 0
        capacity=len(b)
        if not capacity: return 0
        while True:
            if self.offset==len(self.data):
                self.data=self.stream.read(131072); self.offset=0
                if not self.data:
                    if not self.saw or self.expected!=0: raise IOError('truncated zstd stream')
                    self.eof=True; return 0
            src=C.create_string_buffer(self.data); inp=In(C.cast(src,C.c_void_p),len(self.data),self.offset)
            dst=(C.c_char*capacity).from_buffer(b); out=Out(C.cast(dst,C.c_void_p),capacity,0)
            old=self.offset
            self.expected=check(self.lib,self.lib.ZSTD_decompressStream(self.ctx,C.byref(out),C.byref(inp)))
            self.saw=True; self.offset=inp.pos
            if out.pos: return out.pos
            if old==self.offset: raise IOError('zstd stream made no progress')
    def close(self):
        if not self.closed:
            if self.ctx: self.lib.ZSTD_freeDCtx(self.ctx); self.ctx=None
            super().close()
