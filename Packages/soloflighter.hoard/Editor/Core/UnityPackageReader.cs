// What a .unitypackage contains: the GUID and project path of every asset in it, read straight from the
// package (a gzipped tar with a folder per asset holding "asset", "asset.meta" and "pathname"). Nothing is
// extracted or run. Plain C#, no Unity references.
//
// A package is a file anyone could have made, so what its headers claim is checked before it's acted on: only
// names are ever read into memory, and a name longer than any real path is refused before anything is set aside
// for it; a package that would unpack to more than any real one does is refused rather than read to the end.
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Text.RegularExpressions;

namespace SoloFlighter.Hoard
{
    public static class UnityPackageReader
    {
        const int MaxEntries = 500000;
        const int MaxPathname = 4096;
        const long MaxUnpacked = 64L << 30;   // 64 GiB, far beyond any real package: a gzip bomb stops here
        static readonly Regex Guid32 = new Regex("^[0-9a-f]{32}$");

        /// <summary>GUID to project path, for every asset in the package. Throws InvalidDataException if it isn't one.</summary>
        public static Dictionary<string, string> ReadAssets(string packagePath)
        {
            var result = new Dictionary<string, string>();
            using (var file = File.OpenRead(packagePath))
            using (var gz = new GZipStream(file, CompressionMode.Decompress))
            {
                var header = new byte[512];
                string longName = null;
                long unpacked = 0;
                for (int count = 0; count < MaxEntries; count++)
                {
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
                    if (parts.Length == 2 && parts[1] == "pathname" && Guid32.IsMatch(parts[0]) && size <= MaxPathname)
                    {
                        string path = Encoding.UTF8.GetString(ReadBytes(gz, size)).Split('\n')[0].Trim();
                        if (path.Length > 0) result[parts[0]] = path;
                        Skip(gz, Pad(size));
                    }
                    else Skip(gz, size + Pad(size));
                }
            }
            return result;
        }

        static long Pad(long size) { return (512 - size % 512) % 512; }

        static string TarName(byte[] h)
        {
            string name = Field(h, 0, 100), prefix = Field(h, 345, 155);
            bool ustar = Field(h, 257, 6).StartsWith("ustar");
            return ustar && prefix.Length > 0 ? prefix + "/" + name : name;
        }

        static string Field(byte[] h, int at, int len)
        {
            int end = at;
            while (end < at + len && h[end] != 0) end++;
            return Encoding.UTF8.GetString(h, at, end - at);
        }

        static long Octal(byte[] h, int at, int len)
        {
            string s = Field(h, at, len).Trim(' ', '\0');
            if (s.Length == 0) return 0;
            try { return Convert.ToInt64(s, 8); } catch (Exception) { return -1; }
        }

        static bool AllZero(byte[] b) { foreach (byte x in b) if (x != 0) return false; return true; }

        static bool ReadFull(Stream s, byte[] buf, int n)
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

        static void Skip(Stream s, long n)
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
