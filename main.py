import warnings

from transcriber import Transcriber

# logging.basicConfig(level=logging.DEBUG)
warnings.filterwarnings('ignore')

transcriber = Transcriber()
transcriber.start_recording()
