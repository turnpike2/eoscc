
import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from printer import Printer as P
from settings import Config, MissingAbiError, TestFailure

class Test(ABC):
    """
    This class represents a singular test file.
    """

    def __init__(self, cpp_file, test_json, index, test_suite):
        self.cpp_file = cpp_file
        self.test_json = test_json
        self.test_suite = test_suite

        _name = cpp_file.split("/")[-1].split(".")[0]
        self.abi_file = f"{Path(cpp_file).parent}/{_name}.abi"
        self.name = f"{_name}_{index}"

        self.fullname = f"{test_suite.name}/{self.name}"

        self.out_wasm = f"{self.name}.wasm"
        self.success = False

    @abstractmethod
    def _run(self, eosio_cpp: str, args: List[str]):
        pass

    def run(self):
        cf = self.test_json.get("compile_flags")
        args = cf if cf else []

        eosio_cpp = os.path.join(Config.cdt_path, "eosio-cpp")
        self._run(eosio_cpp, args)

    def handle_test_result(self, res: subprocess.CompletedProcess, expected_pass=True):
        stdout = res.stdout.decode("utf-8").strip()
        stderr = res.stderr.decode("utf-8").strip()

        P.print(stdout, verbose=True)
        P.print(stderr, verbose=True)

        if expected_pass and res.returncode > 0:
            self.success = False
            raise TestFailure(
                f"{self.fullname} failed with the following stderr {stderr}",
                failing_test=self,
            )

        if not expected_pass and res.returncode == 0:
            self.success = False
            raise TestFailure(
                "expected to fail compilation/linking but didn't.", failing_test=self
            )

        if not self.test_json.get("expected"):
            self.success = True
        else:
            self.handle_expecteds(res)

    def handle_expecteds(self, res: subprocess.CompletedProcess):
        expected = self.test_json["expected"]

        if expected.get("exit-code"):
            exit_code = expected["exit-code"]

            if res.returncode != exit_code:
                self.success = False
                raise TestFailure(
                    f"expected {exit_code} exit code but got {res.returncode}",
                    failing_test=self,
                )

        if expected.get("stderr"):
            expected_stderr = expected["stderr"]
            actual_stderr = res.stderr.decode("utf-8")

            if expected_stderr not in actual_stderr:
                self.success = False
                raise TestFailure(
                    f"expected {expected_stderr} stderr but got {actual_stderr}",
                    failing_test=self,
                )

        if expected.get("abi"):
            expected_abi = expected["abi"]
            try:
                f = open(self.abi_file)
            except FileNotFoundError:
                raise MissingAbiError(
                    f"{self.abi_file} is missing and expected by {self.fullname}"
                )
            else:
                with f:
                    actual_abi = f.read()

                    if expected_abi != actual_abi:
                        self.success = False
                        raise TestFailure(
                            "actual abi did not match expected abi", failing_test=self
                        )

        if expected.get("wasm"):
            expected_wasm = expected["wasm"]

            xxd = subprocess.Popen(("xxd", "-p", self.out_wasm), stdout=subprocess.PIPE)
            tr = subprocess.check_output(("tr", "-d", "\n"), stdin=xxd.stdout)
            xxd.wait()

            actual_wasm = tr.decode("utf-8")

            if expected_wasm != actual_wasm:
                self.success = False
                raise TestFailure(
                    "actual wasm did not match expected wasm", failing_test=self
                )

        self.success = True

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return self.fullname


class BuildPassTest(Test):
    def _run(self, eosio_cpp, args):
        command = [eosio_cpp, self.cpp_file, "-o", self.out_wasm]
        command.extend(args)
        res = subprocess.run(command, capture_output=True)
        self.handle_test_result(res)

        return res


class CompilePassTest(Test):
    def _run(self, eosio_cpp, args):
        command = [eosio_cpp, "-c", self.cpp_file, "-o", self.out_wasm]
        command.extend(args)
        res = subprocess.run(command, capture_output=True)
        self.handle_test_result(res)

        return res


class AbigenPassTest(Test):
    def _run(self, eosio_cpp, args):
        command = [eosio_cpp, "-abigen", self.cpp_file, "-o", self.out_wasm]
        command.extend(args)
        res = subprocess.run(command, capture_output=True)
        self.handle_test_result(res)

        return res


class BuildFailTest(Test):
    def _run(self, eosio_cpp, args):
        command = [eosio_cpp, self.cpp_file, "-o", self.out_wasm]
        command.extend(args)
        res = subprocess.run(command, capture_output=True)
        self.handle_test_result(res, expected_pass=False)

        return res


class CompileFailTest(Test):
    def _run(self, eosio_cpp, args):
        command = [eosio_cpp, "-c", self.cpp_file, "-o", self.out_wasm]
        command.extend(args)
        res = subprocess.run(command, capture_output=True)
        self.handle_test_result(res, expected_pass=False)

        return res