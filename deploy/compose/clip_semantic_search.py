import gc
import sys

sys.path.insert(0, "/opt/librephotos")
import gpu_runtime

def _allow_local_torch_load():
    noop = lambda: None
    try:
        import transformers.modeling_utils as modeling_utils
        import transformers.utils.import_utils as import_utils

        import_utils.check_torch_load_is_safe = noop
        modeling_utils.check_torch_load_is_safe = noop
    except Exception:
        pass


_allow_local_torch_load()

import numpy as np
import PIL
from sentence_transformers import SentenceTransformer


def _use_legacy_image_processor():
    """sentence-transformers 5.7 treats transformers newer than 4.56.1 as if the
    processor accepts per-modality kwargs. transformers 4.56.2 accepts the call
    but drops return_tensors, so pixel_values stays a list and CLIP crashes with
    'list' object has no attribute 'shape'. The flat processor call still works.
    """
    import sentence_transformers.base.modules.transformer as transformer_module

    transformer_module._TRANSFORMERS_PROCESSOR_SUPPORTS_MODALITY_KWARGS = False


def _open_rgb(path):
    img = PIL.Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


class SemanticSearch:
    model = None
    model_is_loaded = False

    def load(self, model):
        self.load_model(model)
        self.model_is_loaded = True
        pass

    def unload(self):
        del self.model
        self.model = None
        gc.collect()
        self.model_is_loaded = False
        pass

    def load_model(self, model):
        _allow_local_torch_load()
        self.model = SentenceTransformer(model)

    def calculate_clip_embeddings(self, img_paths, model):
        import torch

        if not self.model_is_loaded:
            self.load(model)
        _use_legacy_image_processor()
        imgs = []
        if type(img_paths) is list:
            for path in img_paths:
                try:
                    imgs.append(_open_rgb(path))
                except PIL.UnidentifiedImageError:
                    print(f"Error loading image: {path}")
        else:
            try:
                imgs.append(_open_rgb(img_paths))
            except PIL.UnidentifiedImageError:
                print(f"Error loading image: {img_paths}")

        try:
            on_gpu = gpu_runtime.use_torch_cuda()
            print(f"clip embeddings: device {'cuda' if on_gpu else 'cpu'}")
            imgs_emb = self.model.encode(
                imgs,
                batch_size=32,
                convert_to_tensor=True,
                device="cuda" if on_gpu else "cpu",
            )
            if on_gpu:
                if type(img_paths) is list:
                    magnitudes = list(
                        map(lambda x: np.linalg.norm(x.cpu().numpy()), imgs_emb)
                    )

                    return imgs_emb, magnitudes
                else:
                    img_emb = imgs_emb[0].cpu().numpy().tolist()
                    magnitude = np.linalg.norm(img_emb)

                    return img_emb, magnitude
            else:
                if type(img_paths) is list:
                    magnitudes = map(np.linalg.norm, imgs_emb)
                    return imgs_emb, magnitudes
                else:
                    img_emb = imgs_emb[0].tolist()
                    magnitude = np.linalg.norm(img_emb)

                return img_emb, magnitude
        except Exception as e:
            print(f"Error in calculating clip embeddings: {e}")
            raise e

    def calculate_query_embeddings(self, query, model):
        if not self.model_is_loaded:
            self.load(model)
        _use_legacy_image_processor()

        on_gpu = gpu_runtime.use_torch_cuda()
        query_emb = self.model.encode(
            [query],
            convert_to_tensor=True,
            device="cuda" if on_gpu else "cpu",
        )[0].tolist()
        magnitude = np.linalg.norm(query_emb)

        return query_emb, magnitude
