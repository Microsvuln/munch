import os, sys
import subprocess, time, signal
from collections import OrderedDict
from helper import order_funcs_topologic


def run_afl_cov(prog, path_to_afl_results, code_dir):
    afl_out_res = path_to_afl_results
    output = afl_out_res + "/" + "afl_cov.txt"
    command = "./" + code_dir + " < AFL_FILE"
    print(command)
    pos = code_dir.rfind('/')
    code_dir = code_dir[:pos + 1]
    args = ["afl-cov", "-d", afl_out_res, "-e", command, "-c", code_dir, "--coverage-include-lines", "-O"]
    print(args)
    subprocess.call(args)

    # get function coverage
    cov_dir = afl_out_res + "/cov/"
    filename = cov_dir + "id-delta-cov"
    f_cov = open(filename, "r")
    next(f_cov)

    write_func = cov_dir + "afl_func_cov.txt"
    f = open(write_func, "a+")

    func_list = []
    for line in f_cov:
        words = line.split(" ")
        if "function" in words[3]:
            func_list.append(words[4][:-3])
            f.write(words[4][:-3] + "\n")

    f.close()
    f_cov.close()

    return func_list


def main(argv):
    try:
        afl_binary = sys.argv[1]  # name of the program for afl
        llvm_obj = sys.argv[2]  # name of the program for klee
        testcases = sys.argv[3]  # testcases for the program used by afl-fuzz
        fuzz_time = int(sys.argv[4])  # time to run afl-fuzzer
        gcov_dir = sys.argv[5]  # gcov
        afl_flag = sys.argv[6]
        llvm_flag = sys.argv[7]
    except IndexError:
        print("Wrong number of command line args:", sys.exc_info()[0])
        raise

    # get a list of functions topologically ordered
    args = [os.environ['HOME'] + "/build/llvm/Release/bin/opt", "-load", os.environ['HOME'] + "/build/macke-opt-llvm/bin/libMackeOpt.so",
            llvm_obj, "--listallfuncstopologic", "-disable-output"]
    result = subprocess.check_output(args)
    result = str(result, 'utf-8')
    all_funcs_topologic = order_funcs_topologic(result)
    print("TOTAL FUNCS : ")
    print(len(all_funcs_topologic))
    time.sleep(5)

    uncovered_funcs = []
    if afl_flag == 1:
        # run afl-fuzz
        pos = afl_binary.rfind('/')
        afl_out_dir = afl_binary[:pos + 1] + "afl_results"
        args = ["afl-fuzz", "-i", testcases, "-o", afl_out_dir, afl_binary, "@@"]
        # take the progs args as given from command line
        # if sys.argv[5:]:
        #    args = args + sys.argv[5:]

        print("Preparing to fuzz...")
        time.sleep(3)
        proc = subprocess.Popen(args)

        time.sleep(fuzz_time)
        os.kill(proc.pid, signal.SIGKILL)

        func_list_afl = run_afl_cov(afl_binary, afl_out_dir, gcov_dir)
        print(len(func_list_afl))
        print(func_list_afl)


        print("Computing function coverage after fuzzing...")
        time.sleep(3)

        for index in range(len(all_funcs_topologic)):
            if all_funcs_topologic[index] not in func_list_afl:
                uncovered_funcs.append(all_funcs_topologic[index])

        # save the list of covered and uncovered functions after fuzzing
        cov_funcs = afl_out_dir + "/covered_functions.txt"
        with open(cov_funcs, 'w+') as the_file:
            the_file.write("%s\n" % len(func_list_afl))
            for index in range(len(func_list_afl)):
                the_file.write("%s\n" % func_list_afl[index])

        uncov_funcs = afl_out_dir + "/uncovered_functions.txt"
        with open(uncov_funcs, 'w+') as the_file:
            the_file.write("%s\n" % len(uncovered_funcs))
            for index in range(len(uncovered_funcs)):
                the_file.write("%s\n" % uncovered_funcs[index])

    if llvm_flag == 1:
        func_dir = OrderedDict()
        if afl_flag == 0:
            uncovered_funcs = all_funcs_topologic
        for index in range(len(uncovered_funcs)):
            func = uncovered_funcs[index]
            func_dir[func] = 0

        targ = "-targeted-function="
        covered_from_klee = set()
        pos = llvm_obj.rfind('/')
        klee_cov_funcs = llvm_obj[:pos + 1] + "covered_funcs.txt"
        klee_uncov_funcs = llvm_obj[:pos + 1] + "uncovered_funcs.txt"

        print("Preparing to symbolically execute...")
        time.sleep(3)
        for key in func_dir:
            print(key)
            if func_dir[key] != 1:
                args = [os.environ['HOME'] + "/build/klee/Release+Asserts/bin/klee", "--posix-runtime", "--libc=uclibc",
                        "--only-output-states-covering-new", "--disable-inlining", "--optimize", "--max-time=60",
                        "--watchdog", "-search=ld2t", targ + key, llvm_obj, "--sym-arg 20", "--sym-files 1 100"]
                subprocess.Popen(args)
                time.sleep(65)
                klee_dir = llvm_obj[:pos + 1] + "klee-last/run.istats"
                f = open(klee_dir, "r")

                for line in f:
                    if line[:4] == "cfn=":
                        covered_from_klee.add(line[4:-1])

                for func in covered_from_klee:
                    if func in func_dir:
                        func_dir[func] = 1

        print(func_dir)
        cov_file = open(klee_cov_funcs, 'w+')
        uncov_file = open(klee_uncov_funcs, 'w+')
        for key in func_dir:
            if func_dir[key] == 1:
                cov_file.write("%s\n" % key)
            else:
                uncov_file.write("%s\n" % key)

    return 1


if __name__ == '__main__':
    main(sys.argv[1:])

