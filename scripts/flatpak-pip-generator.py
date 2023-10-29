#!/usr/bin/env python3

__license__ = "MIT"

import argparse
import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from collections import OrderedDict

try:
    import requirements
except ImportError:
    exit('Requirements modules is not installed. Run "pip install requirements-parser"')

parser = argparse.ArgumentParser()
parser.add_argument("packages", nargs="*")
parser.add_argument(
    "--python2", action="store_true", help="Look for a Python 2 package"
)
parser.add_argument(
    "--cleanup", choices=["scripts", "all"], help="Select what to clean up after build"
)
parser.add_argument("--requirements-file", "-r", help="Specify requirements.txt file")
parser.add_argument(
    "--build-only",
    action="store_const",
    dest="cleanup",
    const="all",
    help="Clean up all files after build",
)
parser.add_argument(
    "--build-isolation",
    action="store_true",
    default=False,
    help=(
        "Do not disable build isolation. "
        "Mostly useful on pip that does't "
        "support the feature."
    ),
)
parser.add_argument(
    "--ignore-installed",
    type=lambda s: s.split(","),
    default="",
    help="Comma-separated list of package names for which pip "
    "should ignore already installed packages. Useful when "
    "the package is installed in the SDK but not in the "
    "runtime.",
)
parser.add_argument(
    "--checker-data",
    action="store_true",
    help='Include x-checker-data in output for the "Flatpak External Data Checker"',
)
parser.add_argument("--output", "-o", help="Specify output file name")
parser.add_argument(
    "--runtime",
    help="Specify a flatpak to run pip inside of a sandbox, ensures python version compatibility",
)
parser.add_argument(
    "--yaml", action="store_true", help="Use YAML as output format instead of JSON"
)
parser.add_argument(
    "--ignore-errors",
    action="store_true",
    help="Ignore errors when downloading packages",
)
parser.add_argument(
    "--ignore-pkg",
    nargs="*",
    help="Ignore a package when generating the manifest. Can only be used with a requirements file",
)
opts = parser.parse_args()

if opts.yaml:
    try:
        import yaml
    except ImportError:
        exit('PyYAML modules is not installed. Run "pip install PyYAML"')


def get_pypi_url(name: str, filename: str) -> str:
    url = "https://pypi.org/pypi/{}/json".format(name)
    print("Extracting download url for", name)
    with urllib.request.urlopen(url) as response:
        body = json.loads(response.read().decode("utf-8"))
        for release in body["releases"].values():
            for source in release:
                if source["filename"] == filename:
                    return source["url"]
        raise Exception("Failed to extract url from {}".format(url))


def get_tar_package_url_pypi(name: str, version: str) -> str:
    url = "https://pypi.org/pypi/{}/{}/json".format(name, version)
    with urllib.request.urlopen(url) as response:
        body = json.loads(response.read().decode("utf-8"))
        for ext in ["bz2", "gz", "xz", "zip"]:
            for source in body["urls"]:
                if source["url"].endswith(ext):
                    return source["url"]
        print(body["urls"])
        err = "Failed to get {}-{} source from {}".format(name, version, url)
        raise Exception(err)


def get_package_name(filename: str) -> str:
    if filename.endswith(("bz2", "gz", "xz", "zip")):
        segments = filename.split("-")
        if len(segments) == 2:
            return segments[0]
        return "-".join(segments[: len(segments) - 1])
    elif filename.endswith("whl"):
        segments = filename.split("-")
        if len(segments) == 5:
            return segments[0]
        candidate = segments[: len(segments) - 4]
        # Some packages list the version number twice
        # e.g. PyQt5-5.15.0-5.15.0-cp35.cp36.cp37.cp38-abi3-manylinux2014_x86_64.whl
        if candidate[-1] == segments[len(segments) - 4]:
            return "-".join(candidate[:-1])
        return "-".join(candidate)
    else:
        raise Exception(
            "Downloaded filename: {} does not end with bz2, gz, xz, zip, or whl".format(
                filename
            )
        )


def get_file_version(filename: str) -> str:
    name = get_package_name(filename)
    segments = filename.split(name + "-")
    version = segments[1].split("-")[0]
    for ext in ["tar.gz", "whl", "tar.xz", "tar.gz", "tar.bz2", "zip"]:
        version = version.replace("." + ext, "")
    return version


def get_file_hash(filename: str) -> str:
    sha = hashlib.sha256()
    print("Generating hash for", filename.split("/")[-1])
    with open(filename, "rb") as f:
        while True:
            data = f.read(1024 * 1024 * 32)
            if not data:
                break
            sha.update(data)
        return sha.hexdigest()


def download_tar_pypi(url: str, tempdir: str) -> None:
    with urllib.request.urlopen(url) as response:
        file_path = os.path.join(tempdir, url.split("/")[-1])
        with open(file_path, "x+b") as tar_file:
            shutil.copyfileobj(response, tar_file)


def parse_continuation_lines(fin):
    for line in fin:
        line = line.rstrip("\n")
        while line.endswith("\\"):
            try:
                line = line[:-1] + next(fin).rstrip("\n")
            except StopIteration:
                exit(
                    'Requirements have a wrong number of line continuation characters "\\"'
                )
        yield line


def fprint(string: str) -> None:
    separator = "=" * 72  # Same as `flatpak-builder`
    print(separator)
    print(string)
    print(separator)


packages = []
if opts.requirements_file:
    requirements_file_input = os.path.expanduser(opts.requirements_file)
    try:
        with open(requirements_file_input, "r") as req_file:
            reqs = parse_continuation_lines(req_file)
            reqs_as_str = "\n".join([r.split("--hash")[0] for r in reqs])
            reqs_list_raw = reqs_as_str.splitlines()
            py_version_regex = re.compile(
                r";.*python_version .+$"
            )  # Remove when pip-generator can handle python_version
            reqs_list = [py_version_regex.sub("", p) for p in reqs_list_raw]
            if opts.ignore_pkg:
                reqs_new = "\n".join(i for i in reqs_list if i not in opts.ignore_pkg)
            else:
                reqs_new = reqs_as_str
            packages = list(requirements.parse(reqs_new))
            with tempfile.NamedTemporaryFile(
                "w", delete=False, prefix="requirements."
            ) as req_file:
                req_file.write(reqs_new)
                requirements_file_output = req_file.name
    except FileNotFoundError as err:
        print(err)
        sys.exit(1)

elif opts.packages:
    packages = list(requirements.parse("\n".join(opts.packages)))
    with tempfile.NamedTemporaryFile(
        "w", delete=False, prefix="requirements."
    ) as req_file:
        req_file.write("\n".join(opts.packages))
        requirements_file_output = req_file.name
else:
    if not len(sys.argv) > 1:
        exit("Please specifiy either packages or requirements file argument")
    else:
        exit("This option can only be used with requirements file")

for i in packages:
    if i["name"].lower().startswith("pyqt"):
        print("PyQt packages are not supported by flapak-pip-generator")
        print("However, there is a BaseApp for PyQt available, that you should use")
        print(
            "Visit https://github.com/flathub/com.riverbankcomputing.PyQt.BaseApp for more information"
        )
        sys.exit(0)

with open(requirements_file_output, "r") as req_file:
    use_hash = "--hash=" in req_file.read()

python_version = "2" if opts.python2 else "3"
if opts.python2:
    pip_executable = "pip2"
else:
    pip_executable = "pip3"

if opts.runtime:
    flatpak_cmd = [
        "flatpak",
        "--devel",
        "--share=network",
        "--filesystem=/tmp",
        "--command={}".format(pip_executable),
        "run",
        opts.runtime,
    ]
    if opts.requirements_file:
        if os.path.exists(requirements_file_output):
            prefix = os.path.realpath(requirements_file_output)
            flag = "--filesystem={}".format(prefix)
            flatpak_cmd.insert(1, flag)
else:
    flatpak_cmd = [pip_executable]

output_path = ""

if opts.output:
    output_path = os.path.dirname(opts.output)
    output_package = os.path.basename(opts.output)
elif opts.requirements_file:
    output_package = "python{}-{}".format(
        python_version,
        os.path.basename(opts.requirements_file).replace(".txt", ""),
    )
elif len(packages) == 1:
    output_package = "python{}-{}".format(
        python_version,
        packages[0].name,
    )
else:
    output_package = "python{}-modules".format(python_version)
if opts.yaml:
    output_filename = os.path.join(output_path, output_package) + ".yaml"
else:
    output_filename = os.path.join(output_path, output_package) + ".json"

modules = []
vcs_modules = []
sources = {}

tempdir_prefix = "pip-generator-{}".format(output_package)
with tempfile.TemporaryDirectory(prefix=tempdir_prefix) as tempdir:
    pip_download = flatpak_cmd + [
        "download",
        "--exists-action=i",
        "--dest",
        tempdir,
        "-r",
        requirements_file_output,
    ]
    if use_hash:
        pip_download.append("--require-hashes")

    fprint("Downloading sources")
    cmd = " ".join(pip_download)
    print('Running: "{}"'.format(cmd))
    try:
        subprocess.run(pip_download, check=True)
        os.remove(requirements_file_output)
    except subprocess.CalledProcessError:
        os.remove(requirements_file_output)
        print("Failed to download")
        print("Please fix the module manually in the generated file")
        if not opts.ignore_errors:
            print("Ignore the error by passing --ignore-errors")
            raise

        try:
            os.remove(requirements_file_output)
        except FileNotFoundError:
            pass

    fprint("Downloading arch independent packages")
    for filename in os.listdir(tempdir):
        if not filename.endswith(("bz2", "any.whl", "gz", "xz", "zip")):
            version = get_file_version(filename)
            name = get_package_name(filename)
            url = get_tar_package_url_pypi(name, version)
            print("Deleting", filename)
            try:
                os.remove(os.path.join(tempdir, filename))
            except FileNotFoundError:
                pass
            print("Downloading {}".format(url))
            download_tar_pypi(url, tempdir)

    files = {get_package_name(f): [] for f in os.listdir(tempdir)}

    for filename in os.listdir(tempdir):
        name = get_package_name(filename)
        files[name].append(filename)

    # Delete redundant sources, for vcs sources
    for name in files:
        if len(files[name]) > 1:
            zip_source = False
            for f in files[name]:
                if f.endswith(".zip"):
                    zip_source = True
            if zip_source:
                for f in files[name]:
                    if not f.endswith(".zip"):
                        try:
                            os.remove(os.path.join(tempdir, f))
                        except FileNotFoundError:
                            pass

    vcs_packages = {
        x.name: {"vcs": x.vcs, "revision": x.revision, "uri": x.uri}
        for x in packages
        if x.vcs
    }

    fprint("Obtaining hashes and urls")
    for filename in os.listdir(tempdir):
        name = get_package_name(filename)
        sha256 = get_file_hash(os.path.join(tempdir, filename))

        if name in vcs_packages:
            uri = vcs_packages[name]["uri"]
            revision = vcs_packages[name]["revision"]
            vcs = vcs_packages[name]["vcs"]
            url = "https://" + uri.split("://", 1)[1]
            s = "commit"
            if vcs == "svn":
                s = "revision"
            source = OrderedDict(
                [
                    ("type", vcs),
                    ("url", url),
                    (s, revision),
                ]
            )
            is_vcs = True
        else:
            url = get_pypi_url(name, filename)
            source = OrderedDict([("type", "file"), ("url", url), ("sha256", sha256)])
            if opts.checker_data:
                source["x-checker-data"] = {"type": "pypi", "name": name}
                if url.endswith(".whl"):
                    source["x-checker-data"]["packagetype"] = "bdist_wheel"
            is_vcs = False
        sources[name] = {"source": source, "vcs": is_vcs}

# Python3 packages that come as part of org.freedesktop.Sdk.
system_packages = [
    "cython",
    "easy_install",
    "mako",
    "markdown",
    "meson",
    "pip",
    "pygments",
    "setuptools",
    "six",
    "wheel",
]

fprint("Generating dependencies")
for package in packages:
    if package.name is None:
        print(
            "Warning: skipping invalid requirement specification {} because it is missing a name".format(
                package.line
            ),
            file=sys.stderr,
        )
        print(
            "Append #egg=<pkgname> to the end of the requirement line to fix",
            file=sys.stderr,
        )
        continue
    elif package.name.casefold() in system_packages:
        print(f"{package.name} is in system_packages. Skipping.")
        continue

    if len(package.extras) > 0:
        extras = "[" + ",".join(extra for extra in package.extras) + "]"
    else:
        extras = ""

    version_list = [x[0] + x[1] for x in package.specs]
    version = ",".join(version_list)

    if package.vcs:
        revision = ""
        if package.revision:
            revision = "@" + package.revision
        pkg = package.uri + revision + "#egg=" + package.name
    else:
        pkg = package.name + extras + version

    dependencies = []
    # Downloads the package again to list dependencies

    tempdir_prefix = "pip-generator-{}".format(package.name)
    with tempfile.TemporaryDirectory(
        prefix="{}-{}".format(tempdir_prefix, package.name)
    ) as tempdir:
        pip_download = flatpak_cmd + [
            "download",
            "--exists-action=i",
            "--dest",
            tempdir,
        ]
        try:
            print("Generating dependencies for {}".format(package.name))
            subprocess.run(pip_download + [pkg], check=True, stdout=subprocess.DEVNULL)
            for filename in sorted(os.listdir(tempdir)):
                dep_name = get_package_name(filename)
                if dep_name.casefold() in system_packages:
                    continue
                dependencies.append(dep_name)

        except subprocess.CalledProcessError:
            print("Failed to download {}".format(package.name))

    is_vcs = True if package.vcs else False
    package_sources = []
    for dependency in dependencies:
        if dependency in sources:
            source = sources[dependency]
        elif dependency.replace("_", "-") in sources:
            source = sources[dependency.replace("_", "-")]
        else:
            continue

        if not (not source["vcs"] or is_vcs):
            continue

        package_sources.append(source["source"])

    if package.vcs:
        name_for_pip = "."
    else:
        name_for_pip = pkg

    module_name = "python{}-{}".format(python_version, package.name)

    pip_command = [
        pip_executable,
        "install",
        "--verbose",
        "--exists-action=i",
        "--no-index",
        '--find-links="file://${PWD}"',
        "--prefix=${FLATPAK_DEST}",
        '"{}"'.format(name_for_pip),
    ]
    if package.name in opts.ignore_installed:
        pip_command.append("--ignore-installed")
    if not opts.build_isolation:
        pip_command.append("--no-build-isolation")

    module = OrderedDict(
        [
            ("name", module_name),
            ("buildsystem", "simple"),
            ("build-commands", [" ".join(pip_command)]),
            ("sources", package_sources),
        ]
    )
    if opts.cleanup == "all":
        module["cleanup"] = ["*"]
    elif opts.cleanup == "scripts":
        module["cleanup"] = ["/bin", "/share/man/man1"]

    if package.vcs:
        vcs_modules.append(module)
    else:
        modules.append(module)

modules = vcs_modules + modules
if len(modules) == 1:
    pypi_module = modules[0]
else:
    pypi_module = {
        "name": output_package,
        "buildsystem": "simple",
        "build-commands": [],
        "modules": modules,
    }

print()
with open(output_filename, "w") as output:
    if opts.yaml:

        class OrderedDumper(yaml.Dumper):
            def increase_indent(self, flow=False, indentless=False):
                return super(OrderedDumper, self).increase_indent(flow, False)

        def dict_representer(dumper, data):
            return dumper.represent_dict(data.items())

        OrderedDumper.add_representer(OrderedDict, dict_representer)

        output.write(
            "# Generated with flatpak-pip-generator " + " ".join(sys.argv[1:]) + "\n"
        )
        yaml.dump(pypi_module, output, Dumper=OrderedDumper)
    else:
        output.write(json.dumps(pypi_module, indent=4))
    print("Output saved to {}".format(output_filename))
