// What a .unitypackage contains: the GUID and project path of every asset in it, read straight from the
// package (a gzipped tar with a folder per asset holding "asset", "asset.meta" and "pathname"). Nothing is
// extracted or run. Plain C#, no Unity references.
//
// A package is a file anyone could have made, so what its headers claim is checked before it's acted on: only
// names are ever read into memory, and a name longer than any real path is refused before anything is set aside
// for it; a package that would unpack to more than any real one does is refused rather than read to the end. The one
// exception is a package.json (issue #414: a tool's manifest, with its name and version), read when it's small, with
// at most MaxPending bytes held for files whose names haven't been read yet.
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Text.RegularExpressions;

namespace SoloFlighter.Hoard
{
    /// <summary>Reads what's in a .unitypackage (a gzipped tar): each asset's path and GUID, without unpacking
    /// it.</summary>
    public static class UnityPackageReader
    {
        const int MaxEntries = 500000;
        const int MaxPathname = 4096;
        const long MaxUnpacked = 64L << 30;   // 64 GiB, far beyond any real package: a gzip bomb stops here
        const int MaxManifest = 64 * 1024;     // a package.json larger than this is no tool's
        const int MaxPending = 4 * 1024 * 1024;
        const string Manifest = "/package.json";
        static readonly Regex Guid32 = new Regex("^[0-9a-f]{32}$");

        /// <summary>GUID to project path, for every asset in the package. Throws InvalidDataException if it isn't one.</summary>
        public static Dictionary<string, string> ReadAssets(string packagePath)
        {
            bool any;
            return Read(packagePath, null, null, null, out any);
        }

        /// <summary>As ReadAssets, and the bytes of each package.json in the package (a VPM or Unity package's manifest,
        /// which names it and says its version: issue #414), by its GUID.</summary>
        public static Dictionary<string, string> ReadAssetsAndManifests(string packagePath, out Dictionary<string, byte[]> manifests)
        {
            HashSet<string> files;
            return ReadAssetsAndManifests(packagePath, out manifests, out files, null);
        }

        /// <summary>As ReadAssetsAndManifests, with the GUIDs that are files (the rest are folders). progress (when
        /// given) is told how far through the package the reading is, from 0 to 1, now and then; when it says true, the
        /// reading stops with an OperationCanceledException.</summary>
        public static Dictionary<string, string> ReadAssetsAndManifests(string packagePath, out Dictionary<string, byte[]> manifests,
                                                                        out HashSet<string> files, Func<double, bool> progress)
        {
            manifests = new Dictionary<string, byte[]>(StringComparer.Ordinal);
            files = new HashSet<string>(StringComparer.Ordinal);
            bool any;
            return Read(packagePath, files, manifests, progress, out any);
        }

        /// <summary>GUID to project path, for the files in the package only: not its folders, which a project shares
        /// with every other package that puts something in the same folder (a creator's own folder, say).</summary>
        public static Dictionary<string, string> ReadFiles(string packagePath)
        {
            bool any;
            return ReadFiles(packagePath, out any);
        }

        /// <summary>As ReadFiles; hasManifest says whether the package has a package.json anywhere in it (issue #414: one
        /// without can't carry a tool Hoard for Unity knows, so an import needn't read it again).</summary>
        public static Dictionary<string, string> ReadFiles(string packagePath, out bool hasManifest)
        {
            var files = new HashSet<string>(StringComparer.Ordinal);
            var all = Read(packagePath, files, null, null, out hasManifest);
            var result = new Dictionary<string, string>();
            foreach (var kv in all) if (files.Contains(kv.Key)) result[kv.Key] = kv.Value;
            return result;
        }

        /// <summary>As ReadAssets; withFile (when given) gets each GUID that has a file in the package (a folder has none),
        /// manifests (when given) each package.json's bytes, and anyManifest whether there's a package.json at all.</summary>
        static Dictionary<string, string> Read(string packagePath, HashSet<string> withFile, Dictionary<string, byte[]> manifests,
                                               Func<double, bool> progress, out bool anyManifest)
        {
            var result = new Dictionary<string, string>();
            var pending = new Dictionary<string, byte[]>(StringComparer.Ordinal);   // small files whose names come later
            long held = 0, total = progress == null ? 0 : PackageFile.Size(packagePath);
            anyManifest = false;
            using (var file = new Counted(PackageFile.OpenRead(packagePath)))   // a .unitypackage, or one in a .zip
            using (var gz = new GZipStream(file, CompressionMode.Decompress))
            {
                var header = new byte[512];
                string longName = null;
                long unpacked = 0;
                for (int count = 0; count < MaxEntries; count++)
                {
                    if (progress != null && count % 256 == 0 && progress(total > 0 ? Math.Min(1.0, (double)file.Done / total) : 0))
                        throw new OperationCanceledException();
                    if (!ReadFull(gz, header, 512)) break;
                    if (AllZero(header)) break;                                   // the end of the archive
                    string name = longName ?? TarName(header);
                    longName = null;
                    long size = Octal(header, 124, 12);
                    char type = (char)header[156];
                    if (size < 0) throw new InvalidDataException("not a Unity package");
                    unpacked += 512 + size + Pad(size);                           // what this entry takes, read or skipped
                    if (unpacked > MaxUnpacked) throw new InvalidDataException("the package is larger than any real one");
                    if (type == 'L')                                              // a long name for the next entry
                    {
                        longName = Encoding.UTF8.GetString(ReadBytes(gz, size)).TrimEnd('\0');
                        Skip(gz, Pad(size));
                        continue;
                    }
                    string[] parts = name.Replace('\\', '/').TrimStart('.', '/').Split('/');
                    bool asset = parts.Length == 2 && parts[1] == "asset" && Guid32.IsMatch(parts[0]);
                    if (asset && withFile != null) withFile.Add(parts[0]);
                    if (parts.Length == 2 && parts[1] == "pathname" && Guid32.IsMatch(parts[0]) && size <= MaxPathname)
                    {
                        string path = Encoding.UTF8.GetString(ReadBytes(gz, size)).Split('\n')[0].Trim();
                        if (path.Length > 0) result[parts[0]] = path;
                        if (IsManifest(path)) anyManifest = true;
                        Skip(gz, Pad(size));
                        byte[] early;
                        if (pending.TryGetValue(parts[0], out early))   // its file came first: kept only if it's a package.json
                        {
                            pending.Remove(parts[0]);
                            held -= early.Length;
                            if (IsManifest(path)) manifests[parts[0]] = early;
                        }
                    }
                    else if (manifests != null && asset && size <= MaxManifest)
                    {
                        string known;
                        bool named = result.TryGetValue(parts[0], out known);
                        if (named ? IsManifest(known) : held + size <= MaxPending)
                        {
                            var bytes = new byte[size];
                            if (size > 0 && !ReadFull(gz, bytes, (int)size)) throw new InvalidDataException("the package ends partway");
                            if (named) manifests[parts[0]] = bytes;
                            else { byte[] was; if (pending.TryGetValue(parts[0], out was)) held -= was.Length; pending[parts[0]] = bytes; held += size; }
                            Skip(gz, Pad(size));
                        }
                        else Skip(gz, size + Pad(size));
                    }
                    else Skip(gz, size + Pad(size));
                }
            }
            return result;
        }

        /// <summary>Whether an asset's project path is a package.json: a VPM or Unity package's manifest.</summary>
        static bool IsManifest(string path)
        {
            return path.Replace('\\', '/').EndsWith(Manifest, StringComparison.Ordinal);
        }

        /// <summary>A stream that counts what's been read from it, for how far through a package a reading is.</summary>
        internal sealed class Counted : Stream
        {
            readonly Stream inner;
            readonly bool owns;
            public long Done;
            /// <summary>Count what's read from inner; owns: close inner when this is closed.</summary>
            public Counted(Stream inner, bool owns = true) { this.inner = inner; this.owns = owns; }
            /// <summary>Read from the package, counting.</summary>
            public override int Read(byte[] buffer, int offset, int count) { int n = inner.Read(buffer, offset, count); if (n > 0) Done += n; return n; }
            /// <summary>Close the package.</summary>
            protected override void Dispose(bool disposing) { if (disposing && owns) inner.Dispose(); base.Dispose(disposing); }
            public override bool CanRead { get { return true; } }
            public override bool CanSeek { get { return false; } }
            public override bool CanWrite { get { return false; } }
            public override long Length { get { throw new NotSupportedException(); } }
            public override long Position { get { throw new NotSupportedException(); } set { throw new NotSupportedException(); } }
            /// <summary>Nothing to flush: it only reads.</summary>
            public override void Flush() { }
            /// <summary>Not supported: it's read once, in order.</summary>
            public override long Seek(long offset, SeekOrigin origin) { throw new NotSupportedException(); }
            /// <summary>Not supported: it only reads.</summary>
            public override void SetLength(long value) { throw new NotSupportedException(); }
            /// <summary>Not supported: it only reads.</summary>
            public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
        }

        /// <summary>The padding after a tar entry of that size, to the next 512 bytes.</summary>
        internal static long Pad(long size) { return (512 - size % 512) % 512; }

        /// <summary>A tar entry's name (with its ustar prefix).</summary>
        internal static string TarName(byte[] h)
        {
            string name = Field(h, 0, 100), prefix = Field(h, 345, 155);
            bool ustar = Field(h, 257, 6).StartsWith("ustar");
            return ustar && prefix.Length > 0 ? prefix + "/" + name : name;
        }

        /// <summary>A text field of a tar header, up to its first zero.</summary>
        internal static string Field(byte[] h, int at, int len)
        {
            int end = at;
            while (end < at + len && h[end] != 0) end++;
            return Encoding.UTF8.GetString(h, at, end - at);
        }

        /// <summary>A number field of a tar header (octal, or base-256 for a big one).</summary>
        internal static long Octal(byte[] h, int at, int len)
        {
            string s = Field(h, at, len).Trim(' ', '\0');
            if (s.Length == 0) return 0;
            try { return Convert.ToInt64(s, 8); } catch (Exception) { return -1; }
        }

        /// <summary>Whether a block is all zeros (the end of a tar).</summary>
        internal static bool AllZero(byte[] b) { foreach (byte x in b) if (x != 0) return false; return true; }

        /// <summary>Read exactly n bytes. False when the stream ends first.</summary>
        internal static bool ReadFull(Stream s, byte[] buf, int n)
        {
            int got = 0;
            while (got < n)
            {
                int r = s.Read(buf, got, n - got);
                if (r <= 0) return got == 0 ? false : throw new InvalidDataException("the package ends partway");
                got += r;
            }
            return true;
        }

        // Only names are read into memory, and no real one is longer than MaxPathname: a header claiming more is
        // refused here, before anything is allocated for it.
        static byte[] ReadBytes(Stream s, long n)
        {
            if (n > MaxPathname) throw new InvalidDataException("not a Unity package");
            var buf = new byte[n];
            if (n > 0 && !ReadFull(s, buf, (int)n)) throw new InvalidDataException("the package ends partway");
            return buf;
        }

        /// <summary>Skip n bytes of the stream.</summary>
        internal static void Skip(Stream s, long n)
        {
            var buf = new byte[81920];
            while (n > 0)
            {
                int r = s.Read(buf, 0, (int)Math.Min(buf.Length, n));
                if (r <= 0) throw new InvalidDataException("the package ends partway");
                n -= r;
            }
        }
    }
}
