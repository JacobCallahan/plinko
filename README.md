# Plinko
Plinko is a tool that can identify what tests should be ran against a specific product version. These can either be a base version or diff between versions. Version/Diff information must be generated by tools like APIx or CLIx.

Installation
------------
```pip install .```
or
```python setup.py install```


Usage
-----
```
Usage: plinko [OPTIONS] COMMAND [ARGS]...

Options:
  --debug
  --help   Show this message and exit.

Commands:
  classic
  deep
```

Classic
-------
Plinko classic uses test naming conventions to assume test coverage.
For example, a test named ```test_widget_run``` would assume that the test covers the "run" method of a "widget" feature.

To use classic, provide a compact diff or version export and ```pytest --collect-only``` output to get a file containing all identifiable tests that match the given version/diff. This file location will be printed out at runtime.

**Examples:**

```plinko classic --help```

```plinko classic --apix-diff <path/to/diff-comp.yaml> --pytest-export <path/to/collect.txt>```

You can even run Plinko against multiple interfaces at a time.

```plinko classic --apix-diff <path/to/diff-comp.yaml> --clix-diff <path/to/diff-comp.yaml> --pytest-export <path/to/collect.txt>```

Deep
----
Plinko deep has the ability to inspect the code in a test in order to determine the actual feature coverage of that test. Additionally, it will attempt to dig into function calls it can't immediately attribute to a feature. The extra weight of this recursive coverage discovery is lessened by a smart code importer and recursive depth limit (configurable).

**note:** If your test project relies on external libraries, ensure they are installed in Plinko's environment if you want recursive coverage resolution. Otherwise, Plinko will be unable to dynamically load them.

As with classic, you will need a compact version/diff export from tools like APIx or CLIx. Then provide Plinko with the lowest applicable test directory you can, individual test files also work.

**Examples**

```plinko deep --name robottelo --clix-diff ../clix/CLIs/hammer/6.5.0s2-comp.yaml --test-directory ../robottelo/tests/foreman/cli/test_contentview.py --depth 5 --behavior minimal```

```plinko deep --name robottelo --apix-diff ../apix/APIs/satellite6/6.5.0s2-comp.yaml --test-directory ../robottelo/tests/foreman/api/ --depth 5 --behavior minimal```

Configuration
-------------
Plinko has three configuration options: config.yml, environment variables, command line arguments. Plinko handles prioritizes values of those in reverse order (least to most static)

Note
----
This project only explicitly supports python 3.7+.
