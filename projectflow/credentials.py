"""Windows Credential Manager. Fail closed; never fall back to plaintext."""
import ctypes
import os
from ctypes import wintypes


class Credential(ctypes.Structure):
    _fields_ = [('Flags', wintypes.DWORD), ('Type', wintypes.DWORD), ('TargetName', wintypes.LPWSTR),
                ('Comment', wintypes.LPWSTR), ('LastWritten', wintypes.FILETIME),
                ('CredentialBlobSize', wintypes.DWORD), ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)),
                ('Persist', wintypes.DWORD), ('AttributeCount', wintypes.DWORD),
                ('Attributes', ctypes.c_void_p), ('TargetAlias', wintypes.LPWSTR), ('UserName', wintypes.LPWSTR)]


def api():
    if os.name != 'nt':
        raise ValueError('安全密钥存储不可用：请使用本地 .env，或仅在本次运行中使用密钥')
    lib = ctypes.WinDLL('Advapi32.dll', use_last_error=True)
    lib.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
    lib.CredWriteW.restype = wintypes.BOOL
    lib.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(Credential))]
    lib.CredReadW.restype = wintypes.BOOL
    lib.CredFree.argtypes = [ctypes.c_void_p]
    lib.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    lib.CredDeleteW.restype = wintypes.BOOL
    return lib


def save(target, secret):
    lib = api()
    blob = secret.encode('utf-8')
    buffer = (ctypes.c_ubyte * len(blob))(*blob)
    cred = Credential(Type=1, TargetName=target, CredentialBlobSize=len(blob), CredentialBlob=buffer, Persist=2, UserName='ProjectFlow')
    if not lib.CredWriteW(ctypes.byref(cred), 0):
        raise ValueError('Windows 安全存储失败；密钥未写入磁盘。请改用 .env 或仅本次使用')


def load(target):
    lib = api()
    ptr = ctypes.POINTER(Credential)()
    if not lib.CredReadW(target, 1, 0, ctypes.byref(ptr)):
        return ''
    try:
        return ctypes.string_at(ptr.contents.CredentialBlob, ptr.contents.CredentialBlobSize).decode('utf-8')
    finally:
        lib.CredFree(ptr)


def delete(target):
    lib = api()
    if not lib.CredDeleteW(target, 1, 0) and ctypes.get_last_error() != 1168:
        raise ValueError('无法删除 Windows 凭据')
