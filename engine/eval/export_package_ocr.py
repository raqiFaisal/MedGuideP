"""Export the pinned bilingual EasyOCR recognizers and a RapidOCR text detector."""

from pathlib import Path
import argparse
import hashlib
import json
import shutil
import easyocr
import numpy as np
import onnx
import onnxruntime as ort
import rapidocr_onnxruntime
import torch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("weights", type=Path)
parser.add_argument("output", type=Path)
args=parser.parse_args()
torch.set_num_threads(2)
out=args.output
out.mkdir(parents=True, exist_ok=True)

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

class Export(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model=model

    def forward(self, image):
        features = self.model.FeatureExtraction(image).mean(dim=2).transpose(1, 2)
        return self.model.Prediction(self.model.SequenceModeling(features)).softmax(dim=2)

options=ort.SessionOptions()
options.intra_op_num_threads=2
random_input=np.random.default_rng(381).uniform(-1,1,(1,1,64,256)).astype(np.float32)
checks={}
for tag, langs, name, expected_hash in (
    ("arabic",["ar","en"],"arabic.pth","2a9afd42c374deb98aed0b53c9b77d75e1d00d4e0501f3b0276c54190c89b1a8"),
    ("latin",["en"],"english_g2.pth","e2272681d9d67a04e2dff396b6e95077bc19001f8f6d3593c307b9852e1c29e8"),
):
    if digest(args.weights / name) != expected_hash:
        raise ValueError(f"EasyOCR checkpoint checksum does not match: {name}")
    reader=easyocr.Reader(langs,model_storage_directory=str(args.weights),user_network_directory=str(args.weights/'users'),
                          gpu=False,detector=False,download_enabled=False,quantize=False,verbose=False)
    model=Export(reader.recognizer).eval()
    sample=torch.from_numpy(random_input)
    path=out/f"package_ocr_{tag}.onnx"
    with torch.no_grad():
        baseline=model(sample).numpy()
        torch.onnx.export(model,sample,str(path),dynamo=False,opset_version=17,
                          input_names=["image"], output_names=["probabilities"],
                          dynamic_axes={"image": {3: "width"}, "probabilities": {1: "steps"}})
    onnx.checker.check_model(path)
    alphabet=out/f"package_ocr_{tag}_alphabet.json"
    alphabet.write_text(json.dumps(list(reader.character),ensure_ascii=False)+"\n")
    session=ort.InferenceSession(path,sess_options=options,providers=["CPUExecutionProvider"])
    observed=session.run(None,{"image":random_input})[0]
    difference=float(np.max(np.abs(baseline-observed)))
    assert difference < .002, (tag,difference)
    assert observed.shape[2]==len(reader.character)+1
    wide = np.repeat(random_input, 3, axis=3)
    with torch.no_grad():
        expected_wide = model(torch.from_numpy(wide)).numpy()
    actual_wide = session.run(None, {"image": wide})[0]
    assert np.max(np.abs(expected_wide - actual_wide)) < .002
    checks[tag]={"onnx_sha256":digest(path),"alphabet_sha256":digest(alphabet),"max_probability_difference":difference}
    print(tag, checks[tag], flush=True)

detector=out/"package_ocr_detector.onnx"
shutil.copyfile(Path(rapidocr_onnxruntime.__file__).parent/"models/ch_PP-OCRv4_det_infer.onnx",detector)
onnx.checker.check_model(detector)
det=ort.InferenceSession(detector,sess_options=options,providers=["CPUExecutionProvider"])
assert det.run(None,{det.get_inputs()[0].name:np.zeros((1,3,128,192),np.float32)})[0].shape==(1,1,128,192)
report={"detector_sha256":digest(detector),"architecture":"rapidocr-db-easyocr-bilingual","shape":[1,1,64,"width"],
        "recognizers":checks,"runtime":ort.__version__,"sources":["rapidocr_onnxruntime 1.4.4","EasyOCR 1.7.2 arabic_g1 and english_g2"]}
(out/"package_ocr_export_report.json").write_text(json.dumps(report,indent=2)+"\n")
