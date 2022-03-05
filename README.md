# What is this?

A simplified and python-3 oriented version of the pyrocore tools.

# Why should I use this?

You probably shouldn't, the pyrocore tools are perfectly fine and better supported.

## I really want to, though

```bash
pip install pyrosimple
```

Usage is pretty much the same as regular pyroscope

# What's the point of this then?

I needed something simpler for use with personal tools, this allows me to keep the code base mostly compatible while
completely dropping features I have no need for. There are also several changes that would break existing
integrations, and as such aren't easily suitable for upstream changes.

tl;dr I want to move fast and break things.

# Significant changes

- Simpler poetry-based build/install system
- Everything in one package, no separate pyrobase
  - Use external lib for bencode
- Only supports python 3 and rtorrent 0.9.8
- `lstor --raw` prints json
- Support for jinja2 (tempita's use of eval can chew up a surprising amount of cpu)
