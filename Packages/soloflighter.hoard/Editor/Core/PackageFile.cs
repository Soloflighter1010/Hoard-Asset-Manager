// A package the window can read and import: a .unitypackage file, or one a product came zipped in (as many Booth
// products do), named "<the .zip's path>|<its path in the zip>". A package whose path in the zip has a "|" isn't
// offered, so the name splits at the last ".zip|". Plain C#, no Unity references.
using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace SoloFlighter.Hoard
{
    public static class PackageFile
    {
        const string Mark = ".zip|";

        public static string InZip(string zipPath, string member) { return zipPath + "|" + member; }

        /// <summary>The file on disk (the .zip, for a package in one), and the package's path in the zip (null for a
        /// package that's a file of its own). True for a package in a zip.</summary>
        public static bool Split(string package, out string file, out string member)
        {
            int at = package.LastIndexOf(Mark, StringComparison.OrdinalIgnoreCase);
            if (at < 0) { file = package; member = null; return false; }
            file = package.Substring(0, at + 4);
            member = package.Substring(at + Mark.Length);
            return true;
        }

        public static bool IsZipped(string package) { string f, m; return Split(package, out f, out m); }

        /// <summary>The file on disk: the package, or the .zip it's in.</summary>
        public static string OnDisk(string package) { string f, m; Split(package, out f, out m); return f; }

        /// <summary>The package's own file name ("Hoodie_v2.unitypackage"), wherever it is.</summary>
        public static string Name(string package)
        {
            string f, m;
            return Split(package, out f, out m) ? m.Substring(m.LastIndexOf('/') + 1) : Path.GetFileName(f);
        }

        /// <summary>How the window names it: its file name, or for a package in a zip, "Hoodie.zip › Hoodie_v2.unitypackage".</summary>
        public static string Label(string package)
        {
            string f, m;
            return Split(package, out f, out m) ? Path.GetFileName(f) + " › " + m : Path.GetFileName(f);
        }

        public static bool Exists(string package) { return File.Exists(OnDisk(package)); }

        public static DateTime LastWriteUtc(string package) { return File.GetLastWriteTimeUtc(OnDisk(package)); }

        /// <summary>The package as it is now: a changed file (the .zip, for one in a zip) is read again.</summary>
        public static string Stamp(string package)
        {
            var info = new FileInfo(OnDisk(package));
            return package + "|" + info.Length + "|" + info.LastWriteTimeUtc.Ticks;
        }

        /// <summary>The .unitypackage files in a .zip, as packages (InZip); none for one that can't be read, or whose
        /// packages are locked with a password.</summary>
        public static List<string> PackagesIn(string zipPath)
        {
            var found = new List<string>();
            try
            {
                using (var s = File.OpenRead(zipPath))
                    foreach (var e in ZipReader.List(s))
                        if (!e.Locked && HoardCatalog.IsUnityPackage(e.Name) && e.Name.IndexOf('|') < 0) found.Add(InZip(zipPath, e.Name));
            }
            catch (Exception) { /* not a zip, damaged, or gone: nothing to import from it */ }
            return found;
        }

        /// <summary>Read the package's (gzipped) bytes. The caller disposes the stream.</summary>
        public static Stream OpenRead(string package)
        {
            string file, member;
            if (!Split(package, out file, out member)) return File.OpenRead(file);
            var zip = File.OpenRead(file);
            try
            {
                var entry = ZipReader.List(zip).Find(e => e.Name == member);
                if (entry == null) throw new InvalidDataException("the zip no longer has it");
                return new Owning(ZipReader.Open(zip, entry), zip);
            }
            catch (Exception) { zip.Dispose(); throw; }
        }

        /// <summary>A file Unity can import: the package itself, or for a package in a zip, a copy of it unpacked into
        /// folder (made once for each version of the zip, and checked as it's made). Older copies there go.</summary>
        public static string ForImport(string package, string folder)
        {
            string file, member;
            if (!Split(package, out file, out member)) return file;
            string id;
            using (var sha = SHA256.Create())
                id = BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(Stamp(package)))).Replace("-", "").Substring(0, 16).ToLowerInvariant();
            string dir = Path.Combine(folder, id), dest = Path.Combine(dir, SafeName(Name(package)));
            Tidy(folder, id);
            if (File.Exists(dest)) return dest;
            Directory.CreateDirectory(dir);
            string part = dest + ".part";
            using (var zip = File.OpenRead(file))
            {
                var entry = ZipReader.List(zip).Find(e => e.Name == member);
                if (entry == null) throw new InvalidDataException("the zip no longer has it");
                try
                {
                    using (var into = new FileStream(part, FileMode.Create, FileAccess.Write))
                        ZipReader.CopyTo(zip, entry, into);
                }
                catch (Exception) { File.Delete(part); throw; }   // never half a package left to import
            }
            File.Move(part, dest);
            return dest;
        }

        /// <summary>A package's name as a file name of its own: no folders, nothing Windows refuses.</summary>
        static string SafeName(string name)
        {
            var sb = new StringBuilder();
            foreach (char c in name) sb.Append(c < 32 || "<>:\"/\\|?*".IndexOf(c) >= 0 ? '_' : c);
            string s = sb.ToString().Trim().TrimStart('.');
            return s.Length == 0 || !HoardCatalog.IsUnityPackage(s) ? "package.unitypackage" : s;
        }

        static void Tidy(string folder, string keep)
        {
            try
            {
                if (!Directory.Exists(folder)) return;
                foreach (string d in Directory.GetDirectories(folder))
                    if (Path.GetFileName(d) != keep && Directory.GetLastWriteTimeUtc(d) < DateTime.UtcNow.AddDays(-1))
                        Directory.Delete(d, true);
            }
            catch (Exception) { /* in use, or already gone: tried again next time */ }
        }

        /// <summary>A stream that closes the file it reads from when it's closed.</summary>
        sealed class Owning : Stream
        {
            readonly Stream inner, owner;
            public Owning(Stream inner, Stream owner) { this.inner = inner; this.owner = owner; }
            public override int Read(byte[] buffer, int offset, int count) { return inner.Read(buffer, offset, count); }
            protected override void Dispose(bool disposing)
            {
                if (disposing) { inner.Dispose(); owner.Dispose(); }
                base.Dispose(disposing);
            }
            public override bool CanRead { get { return true; } }
            public override bool CanSeek { get { return false; } }
            public override bool CanWrite { get { return false; } }
            public override long Length { get { throw new NotSupportedException(); } }
            public override long Position { get { throw new NotSupportedException(); } set { throw new NotSupportedException(); } }
            public override void Flush() { }
            public override long Seek(long offset, SeekOrigin origin) { throw new NotSupportedException(); }
            public override void SetLength(long value) { throw new NotSupportedException(); }
            public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
        }
    }
}
