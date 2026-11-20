// Issue #414: a copy of a .unitypackage without some of its assets (a tool the project has already: BundledTools), for
// Unity's import dialog to offer the rest just as it would the whole package. A package is a gzipped tar with a folder
// for each asset, named by its GUID (asset, asset.meta, pathname, preview.png); the left-out assets' entries are
// skipped and every other entry is copied byte for byte. The copy goes in the project's Library folder (never in
// Assets), made once for each version of the package. A package is a file anyone could have made, so its headers are
// held to what UnityPackageReader holds them to. Plain C#, no Unity references.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace SoloFlighter.Hoard
{
    /// <summary>A package without some of its assets.</summary>
    public static class PackageTrim
    {
        const int MaxEntries = 500000;
        const int MaxHeaderData = 64 * 1024;   // a long name's or a pax header's own data: no real one comes near
        const long MaxUnpacked = 64L << 30;
        static readonly Regex Guid32 = new Regex("^[0-9a-f]{32}$");

        /// <summary>A copy of a package file without these assets, in folder: made once for each version of the package
        /// and each set of left-out assets, under the package's own name (Unity's dialog and Hoard's import log name
        /// it). Copies made more than a day ago go.</summary>
        public static string Without(string package, ICollection<string> guids, string folder)
        {
            var info = new FileInfo(package);
            var sorted = new List<string>(guids);
            sorted.Sort(StringComparer.Ordinal);
            string id;
            using (var sha = SHA256.Create())
                id = BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(info.FullName + "|" + info.Length + "|" +
                     info.LastWriteTimeUtc.Ticks + "|" + string.Join(",", sorted.ToArray())))).Replace("-", "").Substring(0, 16).ToLowerInvariant();
            string dir = Path.Combine(folder, id), dest = Path.Combine(dir, info.Name);
            PackageFile.Tidy(folder, id);
            if (File.Exists(dest)) return dest;
            Directory.CreateDirectory(dir);
            string part = dest + ".part";
            try
            {
                using (var from = File.OpenRead(package))
                using (var into = new FileStream(part, FileMode.Create, FileAccess.Write))
                    Copy(from, into, new HashSet<string>(sorted, StringComparer.Ordinal));
            }
            catch (Exception) { File.Delete(part); throw; }   // never half a package left to import
            File.Move(part, dest);
            return dest;
        }

        /// <summary>Copy a package (gzipped) without the assets whose GUIDs are in leaveOut, gzipped. Returns how many
        /// entries were left out. Throws InvalidDataException for what isn't a package.</summary>
        public static int Copy(Stream from, Stream into, ICollection<string> leaveOut)
        {
            int skipped = 0;
            using (var gz = new GZipStream(from, CompressionMode.Decompress, true))
            using (var output = new GZipStream(into, CompressionLevel.Fastest, true))
            {
                var header = new byte[512];
                var held = new MemoryStream();   // a long name or pax header, waiting for the entry it's for
                string heldName = null;
                long unpacked = 0;
                bool ended = false;
                for (int count = 0; ; count++)
                {
                    if (count >= MaxEntries) throw new InvalidDataException("the package has more in it than any real one");
                    if (!UnityPackageReader.ReadFull(gz, header, 512)) break;
                    if (UnityPackageReader.AllZero(header)) { ended = true; break; }
                    long size = UnityPackageReader.Octal(header, 124, 12);
                    if (size < 0) throw new InvalidDataException("not a Unity package");
                    long padded = size + UnityPackageReader.Pad(size);
                    unpacked += 512 + padded;
                    if (unpacked > MaxUnpacked) throw new InvalidDataException("the package is larger than any real one");
                    char type = (char)header[156];
                    if (type == 'L' || type == 'x')   // a long name (GNU) or a pax header: for the entry after it
                    {
                        if (size > MaxHeaderData) throw new InvalidDataException("not a Unity package");
                        var data = new byte[padded];
                        if (padded > 0 && !UnityPackageReader.ReadFull(gz, data, (int)padded)) throw new InvalidDataException("the package ends partway");
                        held.Write(header, 0, 512);
                        held.Write(data, 0, data.Length);
                        string named = type == 'L' ? Encoding.UTF8.GetString(data, 0, (int)size).TrimEnd('\0') : PaxPath(data, (int)size);
                        if (named != null) heldName = named;
                        continue;
                    }
                    string name = heldName ?? UnityPackageReader.TarName(header);
                    if (leaveOut.Contains(GuidOf(name) ?? ""))
                    {
                        UnityPackageReader.Skip(gz, padded);
                        skipped++;
                    }
                    else
                    {
                        held.WriteTo(output);
                        output.Write(header, 0, 512);
                        CopyBytes(gz, output, padded);
                    }
                    held.SetLength(0);
                    heldName = null;
                }
                if (!ended && held.Length > 0) throw new InvalidDataException("the package ends partway");
                output.Write(new byte[1024], 0, 1024);   // the end of the archive
            }
            return skipped;
        }

        /// <summary>The asset an entry is part of: its GUID folder ("./0123…/asset" is 0123…), or null for an entry
        /// that isn't in one.</summary>
        public static string GuidOf(string entryName)
        {
            string[] parts = (entryName ?? "").Replace('\\', '/').TrimStart('.', '/').Split('/');
            return Guid32.IsMatch(parts[0]) ? parts[0] : null;
        }

        /// <summary>The path a pax header gives ("27 path=0123…/pathname\n": each record's length is in bytes), or null
        /// when it gives none.</summary>
        static string PaxPath(byte[] data, int size)
        {
            string found = null;
            int at = 0;
            while (at < size)
            {
                int space = Array.IndexOf(data, (byte)' ', at, size - at);
                int len;
                if (space < 0 || space - at > 9 ||
                    !int.TryParse(Encoding.ASCII.GetString(data, at, space - at), NumberStyles.None, CultureInfo.InvariantCulture, out len) ||
                    len <= space - at + 1 || len > size - at || data[at + len - 1] != (byte)'\n') break;
                string record = Encoding.UTF8.GetString(data, space + 1, at + len - 1 - (space + 1));
                if (record.StartsWith("path=", StringComparison.Ordinal)) found = record.Substring(5);
                at += len;
            }
            return found;
        }

        /// <summary>Copy n bytes from one stream to another.</summary>
        static void CopyBytes(Stream from, Stream into, long n)
        {
            var buf = new byte[81920];
            while (n > 0)
            {
                int r = from.Read(buf, 0, (int)Math.Min(buf.Length, n));
                if (r <= 0) throw new InvalidDataException("the package ends partway");
                into.Write(buf, 0, r);
                n -= r;
            }
        }
    }
}
