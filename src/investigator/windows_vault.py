"""Windows 当前用户的通用凭据。仅按助手自己的目标名读写。"""

import ctypes as ct
from ctypes import wintypes as wt
import os
import re

from .model_api import ModelError


class _Credential(ct.Structure):
    _fields_ = [
        ("Flags", wt.DWORD), ("Type", wt.DWORD), ("TargetName", wt.LPWSTR),
        ("Comment", wt.LPWSTR), ("LastWritten", wt.FILETIME), ("CredentialBlobSize", wt.DWORD),
        ("CredentialBlob", ct.POINTER(ct.c_ubyte)), ("Persist", wt.DWORD),
        ("AttributeCount", wt.DWORD), ("Attributes", ct.c_void_p),
        ("TargetAlias", wt.LPWSTR), ("UserName", wt.LPWSTR),
    ]


def _check_target(target):
    if not re.fullmatch(r"TestFailureInvestigator/DeepSeek/[0-9a-f]{64}", target):
        raise ModelError("不是助手的 DeepSeek 凭据名称。")


class WindowsVault:
    def __init__(self):
        if os.name != "nt":
            raise ModelError("持久保存 API Key 需要 Windows 凭据管理器。")
        self.api = ct.WinDLL("advapi32", use_last_error=True)
        ptr = ct.POINTER(_Credential)
        self.api.CredWriteW.argtypes = [ptr, wt.DWORD]
        self.api.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ct.POINTER(ptr)]
        self.api.CredFree.argtypes = [ct.c_void_p]
        self.api.CredFree.restype = None
        self.api.CredDeleteW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD]

    def read(self, target: str) -> str:
        _check_target(target)
        ptr = ct.POINTER(_Credential)()
        if not self.api.CredReadW(target, 1, 0, ct.byref(ptr)):  # CRED_TYPE_GENERIC
            code = ct.get_last_error()
            if code == 1168:  # ERROR_NOT_FOUND
                return ""
            raise ModelError(f"无法读取 Windows 凭据（错误 {code}）。")
        try:
            cred = ptr.contents
            return ct.string_at(cred.CredentialBlob, cred.CredentialBlobSize).decode("ascii")
        except UnicodeDecodeError:
            raise ModelError("已保存的凭据无效，请更新此账号的 API Key。") from None
        finally:
            self.api.CredFree(ptr)

    def write(self, target: str, key: str):
        _check_target(target)
        encoded = key.encode("ascii")
        blob = (ct.c_ubyte * len(encoded)).from_buffer_copy(encoded)
        cred = _Credential(Type=1, TargetName=target, CredentialBlobSize=len(blob),
                           CredentialBlob=blob, Persist=2)  # CRED_PERSIST_LOCAL_MACHINE
        try:
            if not self.api.CredWriteW(ct.byref(cred), 0):
                raise ModelError(f"无法保存 Windows 凭据（错误 {ct.get_last_error()}）。")
        finally:
            ct.memset(blob, 0, len(blob))

    def delete(self, target: str):
        _check_target(target)
        if not self.api.CredDeleteW(target, 1, 0):
            code = ct.get_last_error()
            if code != 1168:
                raise ModelError(f"无法删除 Windows 凭据（错误 {code}）。")
