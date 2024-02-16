import gzip
import json
from pathlib import Path
from typing import List

from more_itertools import pairwise

from ..audio import AudioWord, get_seconds
from ..ppln import Component, Pipeline

# def run_sync_transcribe(audio):
#     client = speech.SpeechClient()

#     with open(audio.get_file_path(), "rb") as audio_file:
#         content = audio_file.read()

#     rec_audio = speech.RecognitionAudio(content=content)
#     config = speech.RecognitionConfig(
#         encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
#         sample_rate_hertz=16000,
#         language_code=audio.get_language(format='gcp'),
#         enable_word_time_offsets=True,
#         enable_word_confidence=True,
#     )

#     response = client.recognize(config=config, audio=rec_audio)

#     words = []
#     for result in response.results:
#         alternatives = result.alternatives[0]
#         words += [(w.word, w.start_time, w.end_time) for w in alternatives.words]
#     return words


def upload_to_gcs(audio, bucket_name, cloud_dir_path, overwrite=False):
    from google.cloud import storage

    cloud_dir_path = Path(cloud_dir_path)
    cloud_input_path = cloud_dir_path / "input" / audio.file_name

    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)

    input_blob = bucket.blob(str(cloud_input_path))
    gcs_uri = f"gs://{bucket_name}/{str(cloud_input_path)}"

    if input_blob.exists() and not overwrite:
        return gcs_uri

    if not audio.rm_intervals:
        input_blob.upload_from_filename(audio.file_path, content_type=audio.mime_type)
    else:
        bytes = audio.get_bytes()
        input_blob.upload_from_string(bytes, content_type=audio.mime_type)

    return gcs_uri


def run_async_transcribe(audio, bucket_name, cloud_dir_path):
    from google.cloud import speech, speech_v2, storage
    from google.protobuf.json_format import MessageToDict

    client = speech.SpeechClient()
    gcs_uri = upload_to_gcs(audio, bucket_name, cloud_dir_path)

    rec_audio = speech.RecognitionAudio(uri=gcs_uri)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED,
        # sample_rate_hertz=16000,
        sample_rate_hertz=audio.sample_rate,
        language_code="mr-IN",
        audio_channel_count=audio.num_channels,
        enable_word_time_offsets=True,
        enable_word_confidence=True,
        enable_automatic_punctuation=True,
    )
    response = client.long_running_recognize(config=config, audio=rec_audio)

    print("Waiting for operation to complete...")
    response = response.result(timeout=6000)
    response_dict = MessageToDict(response._pb)
    return response_dict


def run_async_transcribe2(audio, bucket_name, cloud_dir_path):
    from google.cloud import speech, speech_v2, storage

    client = speech_v2.SpeechClient()
    gcs_uri = upload_to_gcs(audio, bucket_name, cloud_dir_path)

    config = speech_v2.RecognitionConfig(
        features=speech_v2.RecognitionFeatures(
            enable_word_time_offsets=True, enable_word_confidence=True
        ),
        auto_decoding_config=speech_v2.AutoDetectDecodingConfig(),
        language_codes=["mr-IN"],
        model="long",
    )

    file_metadata = speech_v2.BatchRecognizeFileMetadata(uri=gcs_uri)

    # https://console.cloud.google.com/speech/recognizers/projects%2F1056274885613%2Flocations%2Fasia-southeast1%2Frecognizers%2Fmarathi-recognizer?hl=en&project=handy-post-395813
    # "projects/{project_id}/locations/location/asia-southeast1/recognizers/marathi-recognizer"
    project_id = "handy-post-395813"
    request = speech_v2.BatchRecognizeRequest(
        recognizer=f"projects/{project_id}/locations/global/recognizers/_",
        config=config,
        files=[file_metadata],
        recognition_output_config=speech_v2.RecognitionOutputConfig(
            inline_response_config=speech_v2.InlineOutputConfig(),
        ),
    )

    # Transcribes the audio into text
    operation = client.batch_recognize(request=request)

    print("Waiting for operation to complete...")
    response = operation.result(timeout=120)

    words = []
    for result in response.results:
        alternatives = result.alternatives[0]
        words += [(w.word, w.start_time, w.end_time) for w in alternatives.words]
    return words


@Pipeline.register_component(
    assigns="words",
    depends=[],
    requires=["meta"],
)
class TranscribeAudio(Component):
    class Config:
        bucket_name: str = None
        cloud_dir_path: str = "transcriber"
        overwrite_cloud: bool = False
        compress_output: bool = False
        split_times: List[str] = []

    def build_words(self, results, audio, start_sec=0):
        word_idx = 0

        def get_ms(time_str):
            return int(float(time_str[:-1]) * 1000)

        def build_word(chunk_idx, w):
            nonlocal word_idx
            start_ms, end_ms = start_sec + get_ms(w["startTime"]), start_sec + get_ms(w["endTime"])

            w = AudioWord(
                word_idx=word_idx,
                chunk_idx=chunk_idx,
                text_=w["word"],
                start_ms=start_ms,
                end_ms=end_ms,
                audio=audio,
            )
            word_idx += 1
            return w

        words = []
        for idx, chunk in enumerate(results):
            alts = chunk["alternatives"][0]
            words += [build_word(idx, w) for w in alts["words"]]

        return words

    def __call__(self, audio, cfg):
        print(f"Processing {audio.file_name}")
        from google.cloud import speech

        json_path = Path("output") / f"{audio.file_name}.atr.json.gz"
        if json_path.exists():
            with gzip.open(json_path, "rb") as f:
                response_dict = json.loads(f.read())
            audio_words = self.build_words(response_dict["results"], audio)
        else:
            audio_words = []
            if cfg.split_times:
                split_secs = [get_seconds(t) for t in cfg.split_times]

                split_secs = [0] + split_secs + [audio.duration]

                for idx, (start_sec, end_sec) in enumerate(pairwise(split_secs)):
                    audio_slice = audio.split(start_sec, end_sec, Path("input"))
                    response_dict = run_async_transcribe(
                        audio_slice, cfg.bucket, cfg.cloud_dir_path
                    )

                    # Use a new json path for the split audio
                    json_path = Path("output") / f"{audio_slice.file_name}.atr.json.gz"
                    with gzip.open(json_path, "wb") as f:
                        f.write(bytes(json.dumps(response_dict), encoding="utf-8"))

                    audio_words += self.build_words(response_dict["results"], audio, start_sec)
            else:
                response_dict = run_async_transcribe(audio, cfg.bucket, cfg.cloud_dir_path)
                with gzip.open(json_path, "wb") as f:
                    f.write(bytes(json.dumps(response_dict), encoding="utf-8"))
                audio_words = self.build_words(response_dict["results"], audio)
        audio.words = audio_words
        return audio


## Synchronous
"""

def transcribe_file(speech_file: str) -> speech.RecognizeResponse:
        client = speech.SpeechClient()

    with open(speech_file, "rb") as audio_file:
        content = audio_file.read()

    audio = speech.RecognitionAudio(content=content)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="en-US",
    )

    response = client.recognize(config=config, audio=audio)

    # Each result is for a consecutive portion of the audio. Iterate through
    # them to get the transcripts for the entire audio file.
    for result in response.results:
        # The first alternative is the most likely one for this portion.
        print(f"Transcript: {result.alternatives[0].transcript}")

    return response


from google.cloud import speech_v1p1beta1 as speech


def sample_recognize(storage_uri: str) -> speech.RecognizeResponse:
    Args:
      storage_uri URI for audio file in Cloud Storage, e.g. gs://[BUCKET]/[FILE]

    client = speech.SpeechClient()

    # storage_uri = 'gs://cloud-samples-data/speech/brooklyn_bridge.mp3'

    # The language of the supplied audio
    language_code = "en-US"

    # Sample rate in Hertz of the audio data sent
    sample_rate_hertz = 44100

    # Encoding of audio data sent. This sample sets this explicitly.
    # This field is optional for FLAC and WAV audio formats.
    encoding = speech.RecognitionConfig.AudioEncoding.MP3
    config = {
        "language_code": language_code,
        "sample_rate_hertz": sample_rate_hertz,
        "encoding": encoding,
    }
    audio = {"uri": storage_uri}

    response = client.recognize(config=config, audio=audio)

    for result in response.results:
        # First alternative is the most probable result
        alternative = result.alternatives[0]
        print(f"Transcript: {alternative.transcript}")

"""


""""
def transcribe_gcs_with_word_time_offsets(
    gcs_uri: str,
) -> speech.RecognizeResponse:


    client = speech.SpeechClient()

    audio = speech.RecognitionAudio(uri=gcs_uri)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.FLAC,
        sample_rate_hertz=16000,
        language_code="en-US",
        enable_word_time_offsets=True,
    )

    operation = client.long_running_recognize(config=config, audio=audio)

    print("Waiting for operation to complete...")
    result = operation.result(timeout=90)

    for result in result.results:
        alternative = result.alternatives[0]
        print(f"Transcript: {alternative.transcript}")
        print(f"Confidence: {alternative.confidence}")

        for word_info in alternative.words:
            word = word_info.word
            start_time = word_info.start_time
            end_time = word_info.end_time

            print(
                f"Word: {word}, start_time: {start_time.total_seconds()}, end_time: {end_time.total_seconds()}"
            )

    return result
"""
