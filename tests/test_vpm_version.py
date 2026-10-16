"""VPM versions and ranges (hoard/vpm/version.py), against the cases vrc-get checks its own with.

The range cases are node-semver's (Copyright (c) Isaac Z. Schlueter and Contributors, ISC License), as vrc-get
(MIT) adopted them, with its additions: (prerelease allowed?, range, version).
"""
import unittest

from hoard.vpm.version import (ALLOW, DENY, MINIMUM, DependencyRange, UnityVersion, Version, VersionError,
                               VersionRange, partial_unity)

MATCH = [
    (False, '1.0.0 - 2.0.0', '1.2.3'),
    (False, '^1.2.3+build', '1.2.3'),
    (False, '^1.2.3+build', '1.3.0'),
    (False, '1.2.3-pre+asdf - 2.4.3-pre+asdf', '1.2.3'),
    (False, '1.2.3-pre+asdf - 2.4.3-pre+asdf', '1.2.3-pre.2'),
    (False, '1.2.3-pre+asdf - 2.4.3-pre+asdf', '2.4.3-alpha'),
    (False, '1.2.3+asdf - 2.4.3+asdf', '1.2.3'),
    (False, '1.0.0', '1.0.0'),
    (False, '>=*', '0.2.4'),
    (False, '', '1.0.0'),
    (False, '>1.0.0', '1.1.0'),
    (False, '<=2.0.0', '2.0.0'),
    (False, '<=2.0.0', '1.9999.9999'),
    (False, '<=2.0.0', '0.2.9'),
    (False, '<2.0.0', '1.9999.9999'),
    (False, '<2.0.0', '0.2.9'),
    (False, '>= 1.0.0', '1.0.0'),
    (False, '>=  1.0.0', '1.0.1'),
    (False, '>=   1.0.0', '1.1.0'),
    (False, '> 1.0.0', '1.0.1'),
    (False, '>  1.0.0', '1.1.0'),
    (False, '<=   2.0.0', '2.0.0'),
    (False, '<= 2.0.0', '1.9999.9999'),
    (False, '<=  2.0.0', '0.2.9'),
    (False, '<    2.0.0', '1.9999.9999'),
    (False, '<\t2.0.0', '0.2.9'),
    (False, '>=0.1.97', '0.1.97'),
    (False, '0.1.20 || 1.2.4', '1.2.4'),
    (False, '>=0.2.3 || <0.0.1', '0.0.0'),
    (False, '>=0.2.3 || <0.0.1', '0.2.3'),
    (False, '>=0.2.3 || <0.0.1', '0.2.4'),
    (False, '||', '1.3.4'),
    (False, '2.x.x', '2.1.3'),
    (False, '1.2.x', '1.2.3'),
    (False, '1.2.x || 2.x', '2.1.3'),
    (False, '1.2.x || 2.x', '1.2.3'),
    (False, 'x', '1.2.3'),
    (False, '2.*.*', '2.1.3'),
    (False, '1.2.*', '1.2.3'),
    (False, '1.2.* || 2.*', '2.1.3'),
    (False, '1.2.* || 2.*', '1.2.3'),
    (False, '*', '1.2.3'),
    (False, '2', '2.1.2'),
    (False, '2.3', '2.3.1'),
    (False, '~0.0.1', '0.0.1'),
    (False, '~0.0.1', '0.0.2'),
    (False, '~x', '0.0.9'),
    (False, '~2', '2.0.9'),
    (False, '~2.4', '2.4.0'),
    (False, '~2.4', '2.4.5'),
    (False, '~1', '1.2.3'),
    (False, '~1.0', '1.0.2'),
    (False, '~ 1.0', '1.0.2'),
    (False, '~ 1.0.3', '1.0.12'),
    (False, '>=1', '1.0.0'),
    (False, '>= 1', '1.0.0'),
    (False, '<1.2', '1.1.1'),
    (False, '< 1.2', '1.1.1'),
    (False, '~v0.5.4-pre', '0.5.5'),
    (False, '~v0.5.4-pre', '0.5.4'),
    (False, '=0.7.x', '0.7.2'),
    (False, '<=0.7.x', '0.7.2'),
    (False, '>=0.7.x', '0.7.2'),
    (False, '<=0.7.x', '0.6.2'),
    (False, '~1.2.1 >=1.2.3', '1.2.3'),
    (False, '~1.2.1 =1.2.3', '1.2.3'),
    (False, '~1.2.1 1.2.3', '1.2.3'),
    (False, '~1.2.1 >=1.2.3 1.2.3', '1.2.3'),
    (False, '~1.2.1 1.2.3 >=1.2.3', '1.2.3'),
    (False, '>=1.2.1 1.2.3', '1.2.3'),
    (False, '1.2.3 >=1.2.1', '1.2.3'),
    (False, '>=1.2.3 >=1.2.1', '1.2.3'),
    (False, '>=1.2.1 >=1.2.3', '1.2.3'),
    (False, '>=1.2', '1.2.8'),
    (False, '^1.2.3', '1.8.1'),
    (False, '^0.1.2', '0.1.2'),
    (False, '^0.1', '0.1.2'),
    (False, '^0.0.1', '0.0.1'),
    (False, '^1.2', '1.4.2'),
    (False, '^1.2 ^1', '1.4.2'),
    (False, '^1.2.3-alpha', '1.2.3-pre'),
    (False, '^1.2.0-alpha', '1.2.0-pre'),
    (False, '^0.0.1-alpha', '0.0.1-beta'),
    (False, '^0.0.1-alpha', '0.0.1'),
    (False, '^0.1.1-alpha', '0.1.1-beta'),
    (False, '^x', '1.2.3'),
    (False, 'x - 1.0.0', '0.9.7'),
    (False, 'x - 1.x', '0.9.7'),
    (False, '1.0.0 - x', '1.9.7'),
    (False, '1.x - x', '1.9.7'),
    (False, '<=7.x', '7.9.9'),
    (True, '2.x', '2.0.0-pre.0'),
    (True, '2.x', '2.1.0-pre.0'),
    (True, '1.1.x', '1.1.0-a'),
    (True, '1.1.x', '1.1.1-a'),
    (True, '*', '1.0.0-rc1'),
    (True, '^1.0.0-0', '1.0.1-rc1'),
    (True, '^1.0.0-rc2', '1.0.1-rc1'),
    (True, '^1.0.0', '1.0.1-rc1'),
    (True, '^1.0.0', '1.1.0-rc1'),
    (True, '1 - 2', '2.0.0-pre'),
    (True, '1 - 2', '1.0.0-pre'),
    (True, '1.0 - 2', '1.0.0-pre'),
    (True, '=0.7.x', '0.7.0-asdf'),
    (True, '>=0.7.x', '0.7.0-asdf'),
    (True, '<=0.7.x', '0.7.0-asdf'),
    (True, '>=1.0.0 <=1.1.0', '1.1.0-pre'),
    (True, '1.0.x - 2', '1.0.0-pre'),
    (False, '~3.5.0beta', '3.5.0'),
    (False, '~3.5.0-', '3.5.0'),
]

NO_MATCH = [
    (False, '1.0.0 - 2.0.0', '2.2.3'),
    (False, '1.2.3+asdf - 2.4.3+asdf', '1.2.3-pre.2'),
    (False, '1.2.3+asdf - 2.4.3+asdf', '2.4.3-alpha'),
    (False, '^1.2.3+build', '2.0.0'),
    (False, '^1.2.3+build', '1.2.0'),
    (False, '^1.2.3', '1.2.3-pre'),
    (False, '^1.2', '1.2.0-pre'),
    (False, '>1.2', '1.3.0-beta'),
    (False, '<=1.2.3', '1.2.3-beta'),
    (False, '^1.2.3', '1.2.3-beta'),
    (False, '=0.7.x', '0.7.0-asdf'),
    (False, '>=0.7.x', '0.7.0-asdf'),
    (False, '<=0.7.x', '0.7.0-asdf'),
    (False, '1.0.0', '1.0.1'),
    (False, '>=1.0.0', '0.0.0'),
    (False, '>=1.0.0', '0.0.1'),
    (False, '>=1.0.0', '0.1.0'),
    (False, '>1.0.0', '0.0.1'),
    (False, '>1.0.0', '0.1.0'),
    (False, '<=2.0.0', '3.0.0'),
    (False, '<=2.0.0', '2.9999.9999'),
    (False, '<=2.0.0', '2.2.9'),
    (False, '<2.0.0', '2.9999.9999'),
    (False, '<2.0.0', '2.2.9'),
    (False, '>=0.1.97', '0.1.93'),
    (False, '0.1.20 || 1.2.4', '1.2.3'),
    (False, '>=0.2.3 || <0.0.1', '0.0.3'),
    (False, '>=0.2.3 || <0.0.1', '0.2.2'),
    (False, '2.x.x', '3.1.3'),
    (False, '1.2.x', '1.3.3'),
    (False, '1.2.x || 2.x', '3.1.3'),
    (False, '1.2.x || 2.x', '1.1.3'),
    (False, '2.*.*', '1.1.3'),
    (False, '2.*.*', '3.1.3'),
    (False, '1.2.*', '1.3.3'),
    (False, '1.2.* || 2.*', '3.1.3'),
    (False, '1.2.* || 2.*', '1.1.3'),
    (False, '2', '1.1.2'),
    (False, '2.3', '2.4.1'),
    (False, '~0.0.1', '0.1.0-alpha'),
    (False, '~0.0.1', '0.1.0'),
    (False, '~2.4', '2.5.0'),
    (False, '~2.4', '2.3.9'),
    (False, '~1', '0.2.3'),
    (False, '~1.0', '1.1.0'),
    (False, '<1', '1.0.0'),
    (False, '>=1.2', '1.1.1'),
    (False, '~v0.5.4-beta', '0.5.4-alpha'),
    (False, '=0.7.x', '0.8.2'),
    (False, '>=0.7.x', '0.6.2'),
    (False, '<0.7.x', '0.7.2'),
    (False, '<1.2.3', '1.2.3-beta'),
    (False, '=1.2.3', '1.2.3-beta'),
    (False, '>1.2', '1.2.8'),
    (False, '^0.0.1', '0.0.2-alpha'),
    (False, '^0.0.1', '0.0.2'),
    (False, '^1.2.3', '2.0.0-alpha'),
    (False, '^1.2.3', '1.2.2'),
    (False, '^1.2', '1.1.9'),
    (True, '2.x', '3.0.0-pre.0'),
    (True, '^1.0.0', '1.0.0-rc1'),
    (True, '^1.0.0', '2.0.0-rc1'),
    (True, '^1.2.3-rc2', '2.0.0'),
    (False, '^1.0.0', '2.0.0-rc1'),
    (True, '1 - 2', '3.0.0-pre'),
    (False, '1 - 2', '2.0.0-pre'),
    (False, '1 - 2', '1.0.0-pre'),
    (False, '1.0 - 2', '1.0.0-pre'),
    (False, '1.1.x', '1.0.0-a'),
    (False, '1.1.x', '1.1.0-a'),
    (False, '1.1.x', '1.2.0-a'),
    (True, '1.1.x', '1.2.0-a'),
    (True, '1.1.x', '1.0.0-a'),
    (False, '1.x', '1.0.0-a'),
    (False, '1.x', '1.1.0-a'),
    (False, '1.x', '1.2.0-a'),
    (True, '1.x', '0.0.0-a'),
    (True, '1.x', '2.0.0-a'),
    (False, '>=1.0.0 <1.1.0', '1.1.0'),
    (True, '>=1.0.0 <1.1.0', '1.1.0'),
    (False, '>=1.0.0 <1.1.0', '1.1.0-pre'),
    (False, '>=1.0.0 <1.1.0-pre', '1.1.0-pre'),
]


class Ranges(unittest.TestCase):
    def check(self, cases, expect):
        for pre, text, version in cases:
            with self.subTest(range=text, version=version):
                r, v = VersionRange.parse(text), Version.parse(version)
                self.assertIs(r.match_pre(v, ALLOW) if pre else r.matches(v), expect)

    def test_match(self):
        self.check(MATCH, True)

    def test_no_match(self):
        self.check(NO_MATCH, False)

    def test_prerelease_choices(self):
        r = VersionRange.parse(">=1.0.0")
        self.assertFalse(r.match_pre(Version.parse("1.1.0-beta"), DENY))
        self.assertFalse(r.match_pre(Version.parse("1.1.0-beta"), MINIMUM))
        self.assertTrue(r.match_pre(Version.parse("1.1.0-beta"), ALLOW))
        self.assertTrue(VersionRange.parse(">=1.1.0-alpha").match_pre(Version.parse("1.1.0-beta"), MINIMUM))
        self.assertTrue(VersionRange.parse(">=1.1.0-alpha").contains_pre())
        self.assertFalse(r.contains_pre())

    def test_bad_ranges(self):
        for text in ("1.2.3.4", ">=", "01.2", "abc", "1.2.3 - ", "1.0.0 ||  ", None, "1" * 600):
            with self.subTest(text=text):
                self.assertRaises(VersionError, VersionRange.parse, text)

    def test_written_back(self):
        for text in ("^1.2.3", ">=1.0.0 <2.0.0", "1.x || 2.x", "1.0.0 - 2.0.0", "~3.5.0-beta", "=1.2.3", ""):
            self.assertEqual(str(VersionRange.parse(text)), text)
        self.assertEqual(str(VersionRange.parse("~3.5.0beta")), "~3.5.0-beta")

    def test_intersect(self):
        r = VersionRange.parse(">=1.0.0 || >=3.0.0").intersect(VersionRange.parse("<2.0.0"))
        self.assertEqual(str(r), ">=1.0.0 <2.0.0 || >=3.0.0 <2.0.0")
        self.assertTrue(r.matches(Version.parse("1.5.0")))
        self.assertFalse(r.matches(Version.parse("3.5.0")))


class Versions(unittest.TestCase):
    def test_order(self):
        for greater, lesser in [("0.0.0", "0.0.0-foo"), ("0.0.1", "0.0.0"), ("1.0.0", "0.9.9"), ("0.10.0", "0.9.0"),
                                ("1.2.3", "1.2.3-asdf"), ("1.2.3", "1.2.3-4"), ("1.2.3", "1.2.3-4-foo"),
                                ("1.2.3-5-foo", "1.2.3-5"), ("1.2.3-5", "1.2.3-4"), ("1.2.3-5-foo", "1.2.3-5-Foo"),
                                ("3.0.0", "2.7.2+asdf"), ("1.2.3-a.10", "1.2.3-a.5"), ("1.2.3-a.b", "1.2.3-a.5"),
                                ("1.2.3-a.b", "1.2.3-a"), ("1.2.3-a.b.c.10.d.5", "1.2.3-a.b.c.5.d.100"),
                                ("1.2.3-r2", "1.2.3-r100"), ("1.2.3-r100", "1.2.3-R2")]:
            with self.subTest(greater=greater, lesser=lesser):
                self.assertGreater(Version.parse(greater), Version.parse(lesser))
                self.assertLess(Version.parse(lesser), Version.parse(greater))

    def test_build_is_left_out_of_equality(self):
        self.assertEqual(Version.parse("1.2.3+a"), Version.parse("1.2.3+b"))
        self.assertEqual(len({Version.parse("1.2.3+a"), Version.parse("1.2.3")}), 1)
        self.assertEqual(str(Version.parse("1.2.3-beta.1+exp.sha")), "1.2.3-beta.1+exp.sha")

    def test_bad_versions(self):
        for text in ("1.2", "1.2.3.4", "01.2.3", "1.2.3-", "1.2.3+", "v1.2.3", " 1.2.3", "1.2.3-be ta", "١.2.3", 5):
            with self.subTest(text=text):
                self.assertIsNone(Version.maybe(text))

    def test_dependency_range(self):
        single = DependencyRange.parse("1.2.3")
        self.assertEqual(single.single_version(), Version.parse("1.2.3"))
        self.assertTrue(single.matches(Version.parse("1.9.0")), "a bare version means that one or later")
        self.assertFalse(single.matches(Version.parse("1.2.2")))
        self.assertEqual(str(single.as_range()), ">=1.2.3")
        self.assertEqual(str(DependencyRange.version(Version.parse("2.0.0"))), "2.0.0")
        self.assertEqual(str(DependencyRange.from_version_range(VersionRange.parse("1.2.3"))), "=1.2.3")
        self.assertTrue(DependencyRange.parse("^1.0.0").matches(Version.parse("1.1.0-beta")))


class UnityVersions(unittest.TestCase):
    def test_parse(self):
        for text, parts in [("5.6.6f1", (5, 6, 6, "f", 1, None)), ("2019.1.0a1", (2019, 1, 0, "a", 1, None)),
                            ("2019.4.31f1", (2019, 4, 31, "f", 1, None)), ("2023.3.6c1", (2023, 3, 6, "c", 1, None)),
                            ("2023.3.6p1", (2023, 3, 6, "p", 1, None)), ("2023.3.6x1", (2023, 3, 6, "x", 1, None)),
                            ("2019.1.0a1-EXTRA", (2019, 1, 0, "a", 1, None)),
                            ("2022.3.22f1c1", (2022, 3, 22, "f", 1, 1))]:
            v = UnityVersion.parse(text)
            self.assertEqual((v.major, v.minor, v.revision, v.type, v.increment, v.china), parts, text)
        for text in ("2022", "2019.0", "5.6.6", "2023.4.6f", "2022.3.22f1c0", None):
            self.assertIsNone(UnityVersion.parse(text), text)
        self.assertEqual(UnityVersion.parse_short("2022.3.22"), UnityVersion.parse("2022.3.22f1"))

    def test_order(self):
        p = UnityVersion.parse
        self.assertLess(p("5.6.5f1"), p("5.6.6f1"))
        self.assertLess(p("5.6.6f1"), p("5.6.6f2"))
        self.assertLess(p("5.6.6f1"), p("2022.1.0f1"))
        self.assertLess(p("2022.1.0a1"), p("2022.1.0f1"))
        self.assertLess(p("2022.1.0b9"), p("2022.1.0c1"))
        self.assertEqual(p("2022.3.6f1"), p("2022.3.6c1"), "China's releases are the same release")
        self.assertLess(p("2022.3.6c1"), p("2022.3.6p1"))
        self.assertLess(p("2022.3.6p1"), p("2022.3.6x1"))

    def test_package_unity_field(self):
        self.assertEqual(partial_unity("2022.3"), (2022, 3))
        self.assertEqual(partial_unity(" 2019 "), (2019, 0))
        self.assertIsNone(partial_unity("2022.x"))
        self.assertIsNone(partial_unity(2022))


if __name__ == "__main__":
    unittest.main()
