import inspect
import unittest


class ClientDecodeBoundaryTests(unittest.TestCase):
    def test_new_postprocess_modules_do_not_import_decode_implementations(self):
        from qidian_save import chapter_merge, chapter_preview, proxy

        source = "\n".join(
            inspect.getsource(module)
            for module in (chapter_merge, chapter_preview, proxy)
        ).lower()
        self.assertNotIn("decrypt_qd", source)
        self.assertNotIn("decode_chapter_local", source)
        self.assertNotIn("fock", source)


if __name__ == "__main__":
    unittest.main()
