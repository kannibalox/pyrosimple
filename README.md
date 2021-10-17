# What is this?

A simplified and python-3 oriented version of the pyrocore tools.

# Why should I use this?

You probably shouldn't, the pyrocore tools are perfectly fine.

# What's the point of this then?

I needed something simpler for use with personal tools, this allows me to keep the code base mostly compatible while
completely dropping features I have no need for. There are also several changes that would break existing
integrations, and as such aren't easily suitable for upstream changes.

# Significant changes

- Simpler poetry-based build/install system
- Everything in one package, no separate pyrobase
  - Use external lib for bencode
- Only supports python 3
- `lstor --raw` prints json
