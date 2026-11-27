Option Explicit
Dim fso, shell, here, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
command = """C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe"" " & _
          "-NoProfile -STA -ExecutionPolicy Bypass " & _
          "-File """ & here & "\tray-host.ps1"""
shell.Run command, 0, False
