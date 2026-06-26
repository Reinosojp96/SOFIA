import runpy, pathlib
runpy.run_path(
    str(pathlib.Path(__file__).with_suffix(".py")),
    run_name="__main__"
)
