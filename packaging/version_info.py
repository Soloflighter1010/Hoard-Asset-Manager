"""Write the Windows version resource for Hoard.exe and hoard-cli.exe (the details in a file's Properties):
python packaging/version_info.py  ->  build/version_info.txt"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
version = re.search(r'__version__ = "([^"]+)"', (REPO / "hoard" / "__init__.py").read_text("utf-8")).group(1)
nums = tuple(int(x) for x in re.findall(r"\d+", version)[:3]) + (0,)
out = REPO / "build" / "version_info.txt"
out.parent.mkdir(exist_ok=True)
out.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'SoloFlighter'),
      StringStruct('FileDescription', 'Hoard: your VRChat asset library'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'Hoard'),
      StringStruct('LegalCopyright', 'MIT License. Not affiliated with VRChat, Booth, Gumroad, Jinxxy or Payhip.'),
      StringStruct('OriginalFilename', 'Hoard.exe'),
      StringStruct('ProductName', 'Hoard'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", "utf-8")
print(f"{out.relative_to(REPO)}: Hoard {version}")
