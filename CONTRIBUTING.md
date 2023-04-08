Changes are welcomed! Even if you don't have a lot of technical
experience, there's no such thing as having too much documentation.

# Development

pyrosimple is developed using [poetry](https://python-poetry.org/).
The quickest way to get started is:
```bash
curl -sSL https://install.python-poetry.org | python3 -
git clone https://github.com/kannibalox/pyrosimple.git
cd pyrosimple/
poetry install
```

This will give you a dedicated python environment where you can work
without impacting the rest of your system. To run commands from your
dedicated environment, use `poetry run <command>`. See the
[official poetry docs](https://python-poetry.org/docs/) for more information.

Auto-formatting and linting aren't required for PRs, but if you'd like to use them:
```bash
poetry install --with dev
# Auto-format
poetry run black src/
poetry run isort src/
# Unit test and lint
poetry run 
poetry run pylint src/pyrosimple/
```
