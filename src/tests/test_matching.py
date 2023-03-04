# pylint: disable=
""" Filter condition tests.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""
import logging
import time
import unittest

import parsimonious
import pytest

from box.box import Box

from pyrosimple.util import matching


log = logging.getLogger(__name__)
log.debug("module loaded")


# Some of these are redundant due to the more comprehensive tests
# later on, but it can't hurt to have them here
@pytest.mark.parametrize(
    "cond",
    [
        "//",
        "/test/",
        "/.*/",
        "name=*test*",
        "name=//",
        "name!=//",
        "name=/test/",
        "name=/.*/",
        "name=/.+/",
        "Roger.Rabbit?",
        "name=Roger.Rabbit?",
        "Bang!Bang!Bang!",
        "name=Bang!Bang!Bang!",
        "Æon",
        "name=*Æon*",
        "name==test",
        "number=0",
        "number>0",
        "number>=0",
        "number=+0",
        "number<0",
        "number<=0",
        "number=-0",
        "name=/[0-9]/",
        "number!=0",
        "number<>0",
        "name==/.*/",
        "name=*test*",
        "name=test-test2.mkv",
        'name="The Thing"',
        'name="*The Thing*"',
        "name=test name=test2",
        "name=test OR name=test2",
        "[ name=test OR name=test2 ]",
        "NOT [ name=test OR name=test2 ]",
        "NOT [ name=test name=test2 ]",
        "NOT [ name=test test2 ]",
        "NOT [ name=test OR alias=// ]",
        "test=five [ name=test OR name=test2 ]",
        "test=five NOT [ name=test OR name=test2 ]",
        "test=five OR NOT [ name=test name=test2 ]",
        "test=five OR NOT [ name=test OR name=test2 ]",
        "name=arch-* OR [ alias=Ubuntu loaded>1w ]",
    ],
)
def test_parsim_good_conditions(cond):
    matching.QueryGrammar.parse(cond)


@pytest.mark.parametrize(
    "cond",
    [
        "",
        "NOT",
        "NOT OR",
        "[ name!=name",
        "name==name ]",
    ],
)
def test_parsim_error_conditions(cond):
    with pytest.raises(parsimonious.exceptions.ParseError):
        matching.QueryGrammar.parse(cond)


@pytest.mark.parametrize(
    "cond",
    [
        ["name=*", "custom_test=foo"],
    ],
)
def test_parsim_good_cli_conditions(cond):
    matching.create_matcher(cond)


@pytest.mark.parametrize(
    ("cond", "expected"),
    [
        ("name=arch", '"string.contains_i=$d.name=,\\"arch\\""'),
    ],
)
def test_conditions_prefilter(cond, expected):
    filt = (
        matching.MatcherBuilder().visit(matching.QueryGrammar.parse(cond)).pre_filter()
    )
    assert str(filt) == expected


@pytest.mark.parametrize(
    ("matcher", "item"),
    [
        # Patterns
        ("arch", Box(name="arch")),
        ("name=arch", Box(name="arch")),
        ("name=/arch/i", Box(name="ARCH")),
        (["name=/arch/i"], Box(name="ARCH")),
        ("name=/ar.*/i", Box(name="ARCH")),
        (["custom_1=TV", "OR", "custom_1=Movie"], Box(custom_1="TV")),
        ("name=ARCH", Box(name="ARCH")),
        ("name=rtörrent", Box(name="rtörrent")),
        ("name={{d.alias}}", Box(name="ubuntu", alias="ubuntu")),
        ("name={{d.alias}}*", Box(name="ubuntu-server", alias="ubuntu")),
        ("name=rtör*", Box(name="rtörrent")),
        ("name=arch*", Box(name="arch-linux")),
        ("name=arch* is_complete=yes", Box(name="arch-linux", is_complete=True)),
        ("name=arch*", Box(name="arch linux")),
        ('name="arch *"', Box(name="arch linux")),
        ("arch*", Box(name="arch linux")),
        ('"arch lin*"', Box(name="arch linux")),
        ('name="arch linux"', Box(name="arch linux")),
        ("/(foo|arch)/", Box(name="arch linux")),
        ('name="arch lin*"', Box(name="arch linux")),
        ("name=*arch", Box(name="base-arch")),
        ("name=/arch/", Box(name="base-arch")),
        ("name=/arch$/", Box(name="base-arch")),
        (r"/S\d+E\d+/", Box(name="Test.S03E04.mkv")),
        (r"/s\d+e\d+/i", Box(name="Test.S03E04.mkv")),
        ('message=""', Box(message="")),
        ('message!=""', Box(message="Oh no!")),
        # Booleans
        ("is_complete=no", Box(is_complete=False)),
        # Numbers
        ("ratio>2", Box(ratio=5.0)),
        ("ratio>2 ratio<6.0", Box(ratio=5.0)),
        # Byte numbers
        ("size>1G", Box(size=2 * (1024**3))),
        ("size>1000", Box(size=50000)),
        # Datetimes - duration
        ("leechtime==0", Box(leechtime=None)),
        ("leechtime>1h", Box(leechtime=60 * 60 * 2)),
        ("leechtime<1h", Box(leechtime=60 * 30)),
        # Datetimes - regular
        ("completed>2h", Box(completed=time.time() - (60 * 60 * 2) - 5)),
        ("completed<1h", Box(completed=time.time() - 1)),
        ("completed>09/21/1990", Box(completed=time.time())),
        ("completed>21.09.1990", Box(completed=time.time())),
        ("completed>1990-09-21", Box(completed=time.time())),
        ("completed>1990-09-21T12:00", Box(completed=time.time())),
        ("completed>1990-09-21T12:00:00", Box(completed=time.time())),
        # Tags
        ("tagged=test", Box(tagged=["test", "notest"])),
        ("tagged=notest", Box(tagged=["test", "notest"])),
        ("tagged=:", Box(tagged=[])),
        ('tagged=""', Box(tagged=[])),
        ('tagged!=""', Box(tagged=["foo"])),
        ("tagged!=:", Box(tagged=["bar", "foo"])),
        ("tagged!=notest", Box(tagged=["bar", "foo"])),
        # Files
        (
            "files=test*",
            Box(files=[Box(path="test/test.mkv"), Box(path="test.nfo")]),
        ),
        # Multi-type
        (
            "tagged!=notest is_complete=no",
            Box(tagged=["bar", "foo"], is_complete=False),
        ),
        (
            "[ ratio<1 OR seedtime<1 ] custom_1=TV",
            Box(custom_1="TV", ratio=0.5, seedtime=5),
        ),
        (
            ["[", "ratio=-1", "OR", "seedtime=-1", "]", "custom_1=TV"],
            Box(custom_1="TV", ratio=0.5, seedtime=5),
        ),
        (
            ["custom_1=TV", "OR", "[", "ratio=-1", "OR", "seedtime=-1", "]"],
            Box(custom_1="TV", ratio=1.5, seedtime=5),
        ),
    ],
)
def test_matcher(matcher, item):
    m = matching.create_matcher(matcher)
    assert m.match(item)


@pytest.mark.parametrize(
    ("matcher", "item"),
    [
        ("name=arch", Box(name="ARCH")),
        ("name=ARCH", Box(name="arch")),
        ("name=ARCH name=arch", Box(name="ARCH")),
        (["name=ARCH", "name=arch"], Box(name="ARCH")),
        ("name=arch", Box(name="asdfsafad")),
        ("name!=arch*", Box(name="arch-linux")),
        ("name!=/arch$/", Box(name="base-arch")),
        ("is_complete=yes", Box(is_complete=False)),
        ("ratio<2", Box(ratio=5.0)),
        ("size<1G", Box(size=2 * (1024**3))),
        ("leechtime<1h", Box(leechtime=60 * 60 * 2)),
        ("leechtime>3d", Box(leechtime=None)),
        (
            "leechtime<1h is_complete=yes",
            Box(leechtime=60 * 60 * 2, is_complete=False),
        ),
        ("completed>1h", Box(completed=time.time() - 1)),
        ("completed<09/21/1990", Box(completed=time.time())),
        ("tagged=:test", Box(tagged=["test", "notest"])),
        ("tagged=faketest", Box(tagged=["test", "notest"])),
        ("tagged!=notest", Box(tagged=["test", "notest"])),
        (
            ["[", "ratio=+1", "OR", "seedtime=+8d", "]", "custom_1=TV"],
            Box(custom_1="TV", ratio=0.5, seedtime=5),
        ),
    ],
)
def test_matcher_fail(matcher, item):
    m = matching.create_matcher(matcher)
    assert not m.match(item)


@pytest.mark.parametrize(
    ("matcher", "item"),
    [
        ("name=arch", 'string.contains_i=$d.name=,"arch"'),
        ("name=ARCH", 'string.contains_i=$d.name=,"ARCH"'),
        (["name=arch"], 'string.contains_i=$d.name=,"arch"'),
        ('name="arch linux"', 'string.contains_i=$d.name=,"arch linux"'),
        # Make sure to not process globs that might look like regexes
        (
            'name="Long Movie Name (1979)"',
            'string.contains_i=$d.name=,"Long Movie Name (1979)"',
        ),
        (
            'name="Long Movie Name (1979)*"',
            'string.contains_i=$d.name=,"Long Movie Name (1979)"',
        ),
        ("name=/arch/", 'string.contains_i=$d.name=,"arch"'),
        # Avoid getting trapped in trying to prefilter strings inside
        # regex logic
        ("name=/(arch|foo)k+/", 'string.contains_i=$d.name=,"k"'),
        # Too complex of a regex to properly clean
        ("name=/((arch|ubuntu)|foo)k+/", ""),
        # Regex with a space
        ('message="/not registered/"', 'string.contains_i=$d.message=,"registered"'),
        (["message=/not registered/"], 'string.contains_i=$d.message=,"registered"'),
        # Booleans
        ("is_complete=no", "equal=d.complete=,value=0"),
        ("is_private=yes", "equal=d.is_private=,value=1"),
        # Numbers
        ("size<1G", "less=d.size_bytes=,value=1073741824"),
        ("prio=1", "equal=value=$d.priority=,value=1"),
        ("ratio>1", "greater=value=$d.ratio=,value=1000"),
        ("ratio>=1", "greater=value=$d.ratio=,value=999"),
        ("ratio<1", "less=value=$d.ratio=,value=1000"),
        ("ratio<=1", "less=value=$d.ratio=,value=1001"),
        ("prio=1", "equal=value=$d.priority=,value=1"),
        # Tags
        ("tagged=foo", 'string.contains_i=$d.custom=tags,"foo"'),
        ("tagged=:foo", 'string.contains_i=$d.custom=tags,"foo"'),
        ("tagged=:", "equal=d.custom=tags,cat="),
        ("tagged!=:", 'not="$equal=d.custom=tags,cat="'),
        ("tagged!=:foo", 'not="$string.contains_i=$d.custom=tags,\\"foo\\""'),
        ("tagged!=foo", 'not="$string.contains_i=$d.custom=tags,\\"foo\\""'),
        ("views=test", 'string.contains_i=$d.views=,"test"'),
        # Dates
        (
            "completed>1990-09-21",
            "greater=value=$d.custom=tm_completed,value="
            + str(int(time.mktime(time.strptime("1990-09-20", "%Y-%m-%d")))),
        ),
        # Example of a seemingly easy query that can't be prefiltered
        ("done>0", ""),
    ],
)
def test_matcher_prefilter(matcher, item):
    assert (
        matching.unquote_pre_filter(matching.create_matcher(matcher).pre_filter())
        == item
    )
