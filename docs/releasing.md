# Releasing

Nocek is published on [PyPI](https://pypi.org/project/nocek/) by the `Publish`
workflow (`.github/workflows/publish.yml`), through PyPI's trusted publishing: no
password or token is kept anywhere.

## Once: set up publishing

1. Make accounts on [PyPI](https://pypi.org/account/register/) and
   [TestPyPI](https://test.pypi.org/account/register/) (two separate sites), with
   two-factor authentication.
2. On each, add a pending trusted publisher (Account settings, Publishing, "Add a
   new pending publisher", GitHub):
   - PyPI project name: `nocek`
   - Owner: `kazek`, repository: `nocek`
   - Workflow name: `publish.yml`
   - Environment name: `pypi` on PyPI, `testpypi` on TestPyPI

## Each release

1. Set the version in `src/nocek/__init__.py` (`0.1.0`, `0.1.1`, `0.2.0`, ...) and
   commit it.
2. Try it on TestPyPI: on GitHub, Actions, "Publish", "Run workflow" on `main`. Then,
   on a computer with uv:

   ```
   uv tool install --torch-backend auto --index-url https://test.pypi.org/simple/ \
     --extra-index-url https://pypi.org/simple/ --index-strategy unsafe-best-match nocek
   ```

   TestPyPI takes each version once too, so a second try needs a new version, such
   as `0.1.1rc1`.
3. Publish it: tag the commit and push the tag.

   ```
   git tag v0.1.0
   git push origin v0.1.0
   ```

   The workflow checks that the tag names the version in the code, builds Nocek,
   and publishes it. Users then get it with the install script or
   `uv tool upgrade nocek`.

A version once on PyPI cannot be replaced, only followed by a newer one.
