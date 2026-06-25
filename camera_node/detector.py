import logging
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class DogDetector:
    """
    Wraps a TFLite MobileNet SSD COCO model and returns the highest-confidence
    dog detection score for a given frame.

    Expected model outputs (standard TF Object Detection API TFLite export):
      [0] boxes   — [1, N, 4]  float32  (ymin, xmin, ymax, xmax normalised)
      [1] classes — [1, N]     float32  0-indexed class IDs
      [2] scores  — [1, N]     float32  confidence 0–1
      [3] count   — [1]        float32  number of valid detections
    """

    def __init__(self, model_path: str, labels_path: str, num_threads: int = 4,
                 input_size: int = 300) -> None:
        import tflite_runtime.interpreter as tflite

        self.input_size = input_size
        self.interpreter = tflite.Interpreter(
            model_path=model_path,
            num_threads=num_threads,
        )
        self.interpreter.allocate_tensors()

        self._in  = self.interpreter.get_input_details()
        self._out = self.interpreter.get_output_details()

        self._dog_class_id = self._find_dog_class(labels_path)
        logger.info("DogDetector ready — dog class id=%d", self._dog_class_id)

    # ------------------------------------------------------------------ #

    def detect(self, frame: np.ndarray) -> float:
        """
        Run inference on a raw RGB numpy frame (H×W×3, uint8).
        Returns the highest dog confidence score (0.0 if none found).
        """
        img = Image.fromarray(frame).resize(
            (self.input_size, self.input_size), Image.BILINEAR
        )
        tensor = np.expand_dims(np.array(img, dtype=np.uint8), axis=0)

        self.interpreter.set_tensor(self._in[0]["index"], tensor)
        self.interpreter.invoke()

        classes = self.interpreter.get_tensor(self._out[1]["index"])[0]   # [N]
        scores  = self.interpreter.get_tensor(self._out[2]["index"])[0]   # [N]
        count   = int(self.interpreter.get_tensor(self._out[3]["index"])[0])

        best = 0.0
        for i in range(count):
            if int(classes[i]) == self._dog_class_id:
                best = max(best, float(scores[i]))

        return best

    # ------------------------------------------------------------------ #

    @staticmethod
    def _find_dog_class(labels_path: str) -> int:
        """
        Read the label map and return the 0-indexed class ID for "dog".
        Falls back to 17 (COCO 0-indexed) if the file cannot be parsed.
        """
        try:
            with open(labels_path) as f:
                labels = [line.strip().lower() for line in f]
            for i, label in enumerate(labels):
                if label == "dog" or label.endswith(" dog"):
                    return i
            logger.warning("'dog' not found in label map — defaulting to class 17")
        except OSError:
            logger.warning("Cannot open label map %s — defaulting to class 17", labels_path)
        return 17
