# Migrating from pyrocore

## Configuration

The entire configuration has been moved into a single TOML file (`~/.config/pyrosimple/config.yoml`). While most of the settings have the same name/values, there is currently no way
to automatically migrate the configuration. See the [configuration reference](/configuration) for more information.

Similarly, custom code in `config.py` is still supported but will require changes to work under pyrosimple. For the most part
this will just mean changing the location of libraries and minor tweaks to how the custom fields are initialized.

## CLI

### rtcontrol

Multiple action flags can now be specified and will run in order:

`rtcontrol --flush --exec "print={{d.name}}" --flush`

Some of the query syntax has changed slightly:

* `message=` to match an empty string no longer works. Use `message=""` (escaped to be `message=\"\"` in the shell) instead
* String matching is now case-sensitive. To get the old case-insentivity, add the `i` flag to the end of regexes, e.g. `/UbUnTu/i`
