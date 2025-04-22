import os
import sys
import unittest


current_dir = os.path.dirname(os.path.abspath(sys.modules.get(__name__).__file__))

TEST_DATA_DIR = os.path.join(current_dir, "testdata")

DOC1 = os.path.join(TEST_DATA_DIR, "doc1.tex")


class Test_01_CLI(unittest.TestCase):

    def setUp(self):
        self.files_ro_remove = []


    def tearDown(self):

        for fpath in self.files_ro_remove:
            if os.path.isfile(fpath):
                os.unlink(fpath)
        return super().tearDown()

    def test_01_demacro(self):

        def perform_test(macro_string, res_idx):
            res_path = DOC1.replace(".tex", f"_dm{res_idx}.tex")
            expected_res_path = DOC1.replace(".tex", f"__dm_expected{res_idx}.tex")
            cmd = f"demacro {DOC1} {res_path} -rm {macro_string}"
            return_code = os.system(cmd)
            self.assertEqual(return_code, 0)
            self.files_ro_remove.append(res_path)

            with open(res_path) as fp:
                res_src = fp.read()

            with open(expected_res_path) as fp:
                expected_res_src = fp.read()

            self.assertEqual(res_src, expected_res_src)

        perform_test(macro_string="tcblue", res_idx=1)
        perform_test(macro_string="tcred", res_idx=2)

        # now test both macros at the same time
        perform_test(macro_string="tcred tcblue", res_idx=3)
