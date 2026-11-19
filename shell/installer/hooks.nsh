; Hoard's installer hooks (tauri.conf.json's installerHooks).
;
; Issue #410: uninstalling Hoard takes it out of File Explorer, where hoard/explorer.py put it: its right-click
; options (under this account's Software\Classes), and its icon on the Local sync folder, which Hoard notes in
; Software\Hoard\Explorer (SyncFolder). The icon's desktop.ini is taken away only when it's Hoard's (its first line is
; Hoard's mark), with the hidden .hoard-folder.ico beside it, and the folder's read-only mark only when Hoard put it
; there (the desktop.ini's second line says). Not when an update runs the uninstaller ($UpdateMode): the new Hoard
; puts them back as it starts, so the icon stays where it is.
!macro NSIS_HOOK_PREUNINSTALL
  ${If} $UpdateMode <> 1
    Push $R0
    Push $R1
    Push $R2
    Push $R3
    Push $R4
    DeleteRegKey HKCU "Software\Classes\*\shell\Hoard.Add"
    DeleteRegKey HKCU "Software\Classes\Directory\shell\Hoard.Add"
    DeleteRegKey HKCU "Software\Classes\Directory\shell\Hoard.SyncNow"
    DeleteRegKey HKCU "Software\Classes\Directory\Background\shell\Hoard.SyncNow"
    DeleteRegKey HKCU "Software\Classes\Directory\shell\Hoard.OpenLocal"
    DeleteRegKey HKCU "Software\Classes\Directory\Background\shell\Hoard.OpenLocal"
    ReadRegStr $R0 HKCU "Software\Hoard\Explorer" "SyncFolder"
    ${If} $R0 != ""
    ${AndIf} ${FileExists} "$R0\desktop.ini"
      ClearErrors
      FileOpen $R1 "$R0\desktop.ini" r
      ${IfNot} ${Errors}
        FileRead $R1 $R2   ; (its first line: Hoard's mark, when it's Hoard's)
        FileRead $R1 $R3   ; (its second: whether the folder was read-only before Hoard marked it)
        FileClose $R1
        StrCpy $R2 $R2 21
        ${If} $R2 == "; Hoard's sync folder"
          SetFileAttributes "$R0\desktop.ini" NORMAL
          Delete "$R0\desktop.ini"
          SetFileAttributes "$R0\.hoard-folder.ico" NORMAL
          Delete "$R0\.hoard-folder.ico"
          StrCpy $R3 $R3 25
          ${If} $R3 == "; hoard-readonly-before=0"
            System::Call 'kernel32::GetFileAttributesW(w "$R0") i .R4'
            ${If} $R4 <> -1
              IntOp $R4 $R4 & 0x3126   ; (the attributes a program may set, but read-only)
              ${If} $R4 = 0
                StrCpy $R4 128   ; (FILE_ATTRIBUTE_NORMAL: none)
              ${EndIf}
              System::Call 'kernel32::SetFileAttributesW(w "$R0", i R4)'
            ${EndIf}
          ${EndIf}
          System::Call 'shell32::SHChangeNotify(i 0x2000, i 0x5, w "$R0", p 0)'   ; (Explorer shows it plain at once)
        ${EndIf}
      ${EndIf}
    ${EndIf}
    DeleteRegKey HKCU "Software\Hoard\Explorer"
    DeleteRegKey /ifempty HKCU "Software\Hoard"
    Pop $R4
    Pop $R3
    Pop $R2
    Pop $R1
    Pop $R0
  ${EndIf}
!macroend
