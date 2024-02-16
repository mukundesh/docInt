import hashlib
import multiprocessing
import os
import re
import uuid
from itertools import tee
from typing import List, Union

import sentencepiece as spm
from indicnlp.normalize import indic_normalize
from indicnlp.tokenize import indic_detokenize, indic_tokenize
from indicnlp.tokenize.sentence_tokenize import DELIM_PAT_NO_DANDA, sentence_split
from indicnlp.transliterate import unicode_transliterate

# PWD = os.path.dirname(__file__)
# from sacremoses import MosesDetokenizer, MosesPunctNormalizer, MosesTokenizer
from .flores_codes_map_indic import flores_codes, iso_to_flores
from .normalize_punctuation import punc_norm
from .normalize_regex_inference import EMAIL_PATTERN, normalize


def pairwise(iterable):
    # pairwise('ABCDEFG') --> AB BC CD DE EF FG
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def split_sentences(paragraph: str, lang: str) -> List[str]:
    """
    Splits the input text paragraph into sentences. It uses `moses` for English and
    `indic-nlp` for Indic languages.

    Args:
        paragraph (str): input text paragraph.
        lang (str): flores language code.

    Returns:
        List[str] -> list of sentences.
    """
    if lang == "eng_Latn":
        import pysbd

        seg = pysbd.Segmenter(language="en", clean=False)

        # fails to handle sentence splitting in case of
        # with MosesSentenceSplitter(lang) as splitter:
        #     return splitter([paragraph])
        return seg.segment(paragraph)
        # return sent_tokenize(paragraph)  # noqa this is for en-indic case
    else:
        return sentence_split(paragraph, lang=flores_codes[lang], delim_pat=DELIM_PAT_NO_DANDA)


def add_token(sent: str, src_lang: str, tgt_lang: str, delimiter: str = " ") -> str:
    """
    Add special tokens indicating source and target language to the start of the input sentence.
    The resulting string will have the format: "`{src_lang} {tgt_lang} {input_sentence}`".

    Args:
        sent (str): input sentence to be translated.
        src_lang (str): flores lang code of the input sentence.
        tgt_lang (str): flores lang code in which the input sentence will be translated.
        delimiter (str): separator to add between language tags and input sentence (default: " ").

    Returns:
        str: input sentence with the special tokens added to the start.
    """
    return src_lang + delimiter + tgt_lang + delimiter + sent


def apply_lang_tags(sents: List[str], src_lang: str, tgt_lang: str) -> List[str]:
    """
    Add special tokens indicating source and target language to the start of the each input sentence.
    Each resulting input sentence will have the format: "`{src_lang} {tgt_lang} {input_sentence}`".

    Args:
        sent (str): input sentence to be translated.
        src_lang (str): flores lang code of the input sentence.
        tgt_lang (str): flores lang code in which the input sentence will be translated.

    Returns:
        List[str]: list of input sentences with the special tokens added to the start.
    """
    tagged_sents = []
    for sent in sents:
        tagged_sent = add_token(sent.strip(), src_lang, tgt_lang)
        tagged_sents.append(tagged_sent)
    return tagged_sents


def truncate_long_sentences(sents: List[str]) -> List[str]:
    """
    Truncates the sentences that exceed the maximum sequence length.
    The maximum sequence for the IndicTransv2 model is limited to 256 tokens.

    Args:
        sents (List[str]): list of input sentences to truncate.

    Returns:
        List[str]: list of truncated input sentences.
    """
    MAX_SEQ_LEN = 256
    new_sents = []

    for sent in sents:
        words = sent.split()
        num_words = len(words)
        if num_words > MAX_SEQ_LEN:
            print_str = " ".join(words[:5]) + " .... " + " ".join(words[-5:])
            sent = " ".join(words[:MAX_SEQ_LEN])
            print(
                f"WARNING: Sentence {print_str} truncated to 256 tokens as it exceeds maximum length limit"
            )

        new_sents.append(sent)

    return new_sents


class Model:
    """
    Model class to run the IndicTransv2 models using python interface.
    """

    def __init__(
        self,
        ckpt_dir: str,
        device: str = "cuda",
    ):
        """
        Initialize the model class.

        Args:
            ckpt_dir (str): path of the model checkpoint directory.
            device (str, optional): where to load the model (defaults: cuda).
        """
        self.ckpt_dir = ckpt_dir
        # self.en_tok = MosesTokenizer(lang="en")
        # self.en_normalizer = MosesPunctNormalizer()
        # self.en_detok = MosesDetokenizer(lang="en")

        self.xliterator = unicode_transliterate.UnicodeIndicTransliterator()

        print("Initializing sentencepiece model for SRC and TGT")
        self.sp_src = spm.SentencePieceProcessor(
            model_file=os.path.join(ckpt_dir, "vocab", "model.SRC")
        )
        self.sp_tgt = spm.SentencePieceProcessor(
            model_file=os.path.join(ckpt_dir, "vocab", "model.TGT")
        )

        self.input_lang_code_format = "flores"

        self.max_batch_size = 1024
        self.num_threads = multiprocessing.cpu_count() // 2
        self.queue_len = 4

        print("Initializing model for translation")
        # initialize the model
        import ctranslate2

        self.translator = ctranslate2.Translator(
            self.ckpt_dir,
            device=device,
            inter_threads=self.num_threads,
            intra_threads=1,
        )  # , compute_type="auto")

    def get_errors(self, lines, translations):
        error_count = 0
        for ln, t in zip(lines, translations):
            if abs(len(ln) - len(t)) < 0.25 * len(ln):
                error_count += 1
        return error_count

    def translate_lines(self, lines: List[str]) -> List[str]:
        tokenized_sents = [x.strip().split(" ") for x in lines]
        translations = self.translator.translate_batch(
            tokenized_sents,
            max_batch_size=self.max_batch_size,
            batch_type="tokens",
            max_input_length=160,
            max_decoding_length=256,
            beam_size=2,
        )
        translations = [" ".join(x.hypotheses[0]) for x in translations]

        assert len(translations) == len(lines)
        print(f"#Lines: {len(lines)} #Tokens: {sum(len(s) for s in tokenized_sents)}", end=" ")
        print(f"*** Error Counts: {self.get_errors(lines, translations)}")
        return translations

    def translate_lines_async(self, lines_group: List[List[str]]) -> List[str]:
        async_results = []
        for lines in lines_group:
            tokenized_sents = [x.strip().split(" ") for x in lines]
            async_results.extend(
                self.translator.translate_batch(
                    tokenized_sents,
                    max_batch_size=self.max_batch_size,
                    batch_type="tokens",
                    max_input_length=160,
                    max_decoding_length=256,
                    beam_size=2,
                    asynchronous=True,
                )
            )

        trans_sents = []
        for async_result in async_results:
            trans_sents.append(" ".join(async_result.result().hypotheses[0]))

        trans_group, start = [], 0
        for lines in lines_group:
            trans_group.append(trans_sents[start : start + len(lines)])
            start = len(lines)

        return trans_group

    def get_partition_size(self):
        return self.max_batch_size * self.num_threads * self.queue_len

    def group_paragraphs(self, paragraphs, src_lang, tgt_lang):
        all_para_num_tokens = []
        for paragraph in paragraphs:
            sents = split_sentences(paragraph, src_lang)
            preprocessed_sents = self.preprocess_batch(sents, src_lang, tgt_lang)
            para_tokens = 0
            for sent in preprocessed_sents:
                para_tokens += len(sent.strip().split(" "))
            all_para_num_tokens.append(para_tokens)

        assert len(all_para_num_tokens) == len(paragraphs)

        para_batch_size = self.get_partition_size()

        partitions, prev_tokens = [0], 0
        for idx, num_para_tokens in enumerate(all_para_num_tokens):
            if (num_para_tokens + prev_tokens) > para_batch_size:
                partitions.append(idx)
                prev_tokens = num_para_tokens
            else:
                prev_tokens += num_para_tokens
        # end for
        partitions.append(len(all_para_num_tokens))
        return partitions

    def group_paragraphs_yield(self, paragraphs, src_lang, tgt_lang):
        all_para_num_tokens = []
        for paragraph in paragraphs:
            sents = split_sentences(paragraph, src_lang)
            preprocessed_sents = self.preprocess_batch(sents, src_lang, tgt_lang)
            para_tokens = 0
            for sent in preprocessed_sents:
                para_tokens += len(sent.strip().split(" "))
            all_para_num_tokens.append(para_tokens)

        assert len(all_para_num_tokens) == len(paragraphs)

        para_batch_size = self.get_partition_size()

        partitions, prev_tokens = [0], 0
        for idx, num_para_tokens in enumerate(all_para_num_tokens):
            if (num_para_tokens + prev_tokens) > para_batch_size:
                partitions.append(idx)
                prev_tokens = num_para_tokens
            else:
                prev_tokens += num_para_tokens
        # end for
        partitions.append(len(all_para_num_tokens))
        return partitions

    def group_sents(self, sents, src_lang, tgt_lang):
        preprocessed_sents = self.preprocess_batch(sents, src_lang, tgt_lang)
        sent_tokens = [len(s.strip().split(" ")) for s in preprocessed_sents]

        sent_batch_size = self.get_partition_size()
        partitions, prev_tokens = [0], 0
        for idx, num_sent_tokens in enumerate(sent_tokens):
            if (num_sent_tokens + prev_tokens) > sent_batch_size:
                partitions.append(idx)
                prev_tokens = num_sent_tokens
            else:
                prev_tokens += num_sent_tokens
        partitions.append(len(sent_tokens))
        return partitions

    # translate a batch of sentences from src_lang to tgt_lang
    def batch_translate(self, batch, src_lang: str, tgt_lang: str) -> List[str]:
        """
        Translates a batch of input sentences (including pre/post processing)
        from source language to target language.

        Args:
            batch (List[str]): batch of input sentences to be translated.
            src_lang (str): flores source language code.
            tgt_lang (str): flores target language code.

        Returns:
            List[str]: batch of translated-sentences generated by the model.
        """

        assert isinstance(batch, (list, set)), f" batch expected list is of {type(batch)}"

        if self.input_lang_code_format == "iso":
            src_lang, tgt_lang = iso_to_flores[src_lang], iso_to_flores[tgt_lang]

        preprocessed_sents = self.preprocess_batch(batch, src_lang, tgt_lang)
        translations = self.translate_lines(preprocessed_sents)
        return self.postprocess_batch(translations, tgt_lang, input_sents=batch)

    # translate a batch of sentences from src_lang to tgt_lang
    def batch_translate2(self, batch, src_lang: str, tgt_lang: str) -> List[str]:
        """
        Translates a batch of input sentences (including pre/post processing)
        from source language to target language.

        Args:
            batch (List[str]): batch of input sentences to be translated.
            src_lang (str): flores source language code.
            tgt_lang (str): flores target language code.

        Returns:
            List[str]: batch of translated-sentences generated by the model.
        """

        assert isinstance(batch, (list, set)), f" batch expected list is of {type(batch)}"

        if self.input_lang_code_format == "iso":
            src_lang, tgt_lang = iso_to_flores[src_lang], iso_to_flores[tgt_lang]

        preprocessed_sents = self.preprocess_batch(batch, src_lang, tgt_lang)

        num_tokens, batch_sents, translations = 0, [], []
        for sent in preprocessed_sents:
            num_sent_tokens = len(sent.strip().split(" "))
            if num_tokens + num_sent_tokens >= self.max_batch_size:
                translations += self.translate_lines(batch_sents)
                batch_sents.clear()
                num_tokens = 0
            batch_sents.append(sent)
            num_tokens += num_sent_tokens
        # translations = self.translate_lines(preprocessed_sents)

        if batch_sents:
            translations += self.translate_lines(batch_sents)

        return self.postprocess_batch(translations, tgt_lang, input_sents=batch)

    # translate a paragraph from src_lang to tgt_lang
    def translate_paragraph(self, paragraph: str, src_lang: str, tgt_lang: str) -> str:
        """
        Translates an input text paragraph (including pre/post processing)
        from source language to target language.

        Args:
            paragraph (str): input text paragraph to be translated.
            src_lang (str): flores source language code.
            tgt_lang (str): flores target language code.

        Returns:
            str: paragraph translation generated by the model.
        """

        assert isinstance(paragraph, str)

        if self.input_lang_code_format == "iso":
            flores_src_lang = iso_to_flores[src_lang]
        else:
            flores_src_lang = src_lang

        sents = split_sentences(paragraph, flores_src_lang)
        postprocessed_sents = self.batch_translate(sents, src_lang, tgt_lang)
        translated_paragraph = " ".join(postprocessed_sents)

        return translated_paragraph

    # translate a paragraph from src_lang to tgt_lang
    def translate_paragraphs(
        self, paragraphs: List[str], src_lang: str, tgt_lang: str
    ) -> List[str]:
        """
        Translates an input list of text paragraphs (including pre/post processing)
        from source language to target language.

        Args:
            paragraphs (List[str]): input text paragraph to be translated.
            src_lang (str): flores source language code.
            tgt_lang (str): flores target language code.

        Returns:
            List[str]: paragraphs translation generated by the model.
        """

        assert isinstance(paragraphs, list)

        if self.input_lang_code_format == "iso":
            flores_src_lang = iso_to_flores[src_lang]
        else:
            flores_src_lang = src_lang

        all_sents, sent_partitions = [], [0]
        for paragraph in paragraphs:
            sents = split_sentences(paragraph, flores_src_lang)
            all_sents.extend(sents)
            sent_partitions.append(len(all_sents))

        postprocessed_sents = self.batch_translate(all_sents, src_lang, tgt_lang)
        assert len(all_sents) == len(postprocessed_sents)

        translated_paragraphs = []
        for s, e in pairwise(sent_partitions):
            translated_paragraphs.append(" ".join(postprocessed_sents[s:e]))

        return translated_paragraphs

    def preprocess_batch(self, batch: List[str], src_lang: str, tgt_lang: str) -> List[str]:
        """
        Preprocess an array of sentences by normalizing, tokenization, and possibly transliterating it.

        Args:
            batch (List[str]): input list of sentences to preprocess.
            src_lang (str): flores language code of the input text sentences.
            tgt_lang (str): flores language code of the output text sentences.

        Returns:
            str: preprocessed input text sentence.
        """
        preprocessed_sents = self.preprocess(batch, lang=src_lang)
        tokenized_sents = self.apply_spm(preprocessed_sents)
        tagged_sents = apply_lang_tags(tokenized_sents, src_lang, tgt_lang)
        tagged_sents = truncate_long_sentences(tagged_sents)

        return tagged_sents

    def apply_spm(self, sents: List[str]) -> List[str]:
        """
        Applies sentence piece encoding to the batch of input sentences.

        Args:
            sents (List[str]): batch of the input sentences.

        Returns:
            List[str]: batch of encoded sentences with sentence piece model
        """
        return [" ".join(self.sp_src.encode(sent, out_type=str)) for sent in sents]

    def preprocess_sent(
        self, sent: str, normalizer: indic_normalize.IndicNormalizerFactory, lang: str
    ) -> str:
        """
        Preprocess an input text sentence by normalizing, tokenization, and possibly transliterating it.

        Args:
            sent (str): input text sentence to preprocess.
            normalizer (Union[MosesPunctNormalizer, indic_normalize.IndicNormalizerFactory]): an object that performs normalization on the text.
            lang (str): flores language code of the input text sentence.

        Returns:
            str: preprocessed input text sentence.
        """
        iso_lang = flores_codes[lang]
        sent = punc_norm(sent, iso_lang)
        sent = normalize(sent)

        transliterate = True
        if lang.split("_")[1] in ["Arab", "Olck", "Mtei", "Latn"]:
            transliterate = False

        pattern = r"<dnt>(.*?)</dnt>"
        raw_matches = re.findall(pattern, sent)

        if iso_lang == "en":
            processed_sent = " ".join(
                self.en_tok.tokenize(self.en_normalizer.normalize(sent.strip()), escape=False)
            )
            return processed_sent
        elif transliterate:
            # transliterates from the any specific language to devanagari
            # which is why we specify lang2_code as "hi".
            processed_sent = unicode_transliterate.UnicodeIndicTransliterator.transliterate(
                " ".join(
                    indic_tokenize.trivial_tokenize(normalizer.normalize(sent.strip()), iso_lang)
                ),
                iso_lang,
                "hi",
            ).replace(" ् ", "्")
        else:
            # we only need to transliterate for joint training
            processed_sent = " ".join(
                indic_tokenize.trivial_tokenize(normalizer.normalize(sent.strip()), iso_lang)
            )

        processed_sent = processed_sent.replace("< dnt >", "<dnt>")
        processed_sent = processed_sent.replace("< / dnt >", "</dnt>")

        processed_sent_matches = re.findall(pattern, processed_sent)
        for raw_match, processed_sent_match in zip(raw_matches, processed_sent_matches):
            processed_sent = processed_sent.replace(processed_sent_match, raw_match)

        return processed_sent

    def preprocess(self, sents: List[str], lang: str) -> List[str]:
        """
        Preprocess a batch of input sentences for the translation.

        Args:
            sents (List[str]): batch of input sentences to preprocess.
            lang (str): flores language code of the input sentences.

        Returns:
            List[str]: preprocessed batch of input sentences.
        """

        # -------------------------------------------------------
        # Moved inside `preprocess_sent()`
        # normalize punctuations

        # fname = str(uuid.uuid4())
        # with open(f"{fname}.txt", "w", encoding="utf-8") as f:
        #     f.write("\n".join(batch))

        # os.system(f"bash {PWD}/normalize_punctuation.sh {src_lang} < {fname}.txt > {fname}.txt._norm")

        # with open(f"{fname}.txt._norm", "r", encoding="utf-8") as f:
        #     batch = f.read().split("\n")

        # os.unlink(f"{fname}.txt")
        # os.unlink(f"{fname}.txt._norm")
        # -------------------------------------------------------

        if lang == "eng_Latn":
            processed_sents = [self.preprocess_sent(sent, None, lang) for sent in sents]
        else:
            normfactory = indic_normalize.IndicNormalizerFactory()
            normalizer = normfactory.get_normalizer(flores_codes[lang])

            processed_sents = [self.preprocess_sent(sent, normalizer, lang) for sent in sents]

        return processed_sents

    def postprocess_batch(
        self, translations: List[str], lang: str, input_sents: List[str] = None
    ) -> List[str]:
        postprocessed_sents = self.postprocess(translations, lang)

        if input_sents:
            # find the emails in the input sentences and then
            # trim the additional spaces in the generated translations
            matches = [re.findall(EMAIL_PATTERN, x) for x in input_sents]

            for i in range(len(postprocessed_sents)):
                for match in matches[i]:
                    potential_match = match.replace("@", "@ ")
                    postprocessed_sents[i] = postprocessed_sents[i].replace(potential_match, match)

        return postprocessed_sents

    def postprocess(self, sents: List[str], lang: str, common_lang: str = "hin_Deva") -> List[str]:
        """
        Postprocesses a batch of input sentences after the translation generations.

        Args:
            sents (List[str]): batch of translated sentences to postprocess.
            lang (str): flores language code of the input sentences.
            common_lang (str, optional): flores language code of the transliterated language (defaults: hin_Deva).

        Returns:
            List[str]: postprocessed batch of input sentences.
        """
        sents = [self.sp_tgt.decode(x.split(" ")) for x in sents]

        postprocessed_sents = []

        if lang == "eng_Latn":
            for sent in sents:
                # outfile.write(en_detok.detokenize(sent.split(" ")) + "\n")
                # postprocessed_sents.append(self.en_detok.detokenize(sent.split(" ")))
                postprocessed_sents.append(detokenize(sent))
        else:
            for sent in sents:
                outstr = indic_detokenize.trivial_detokenize(
                    self.xliterator.transliterate(
                        sent, flores_codes[common_lang], flores_codes[lang]
                    ),
                    flores_codes[lang],
                )
                postprocessed_sents.append(outstr)

        return postprocessed_sents


def detokenize(text):
    # Remove space before punctuation characters
    text = re.sub(r"\s+([^\w\s\(\[\{])", r"\1", text)
    # Remove space after ( [ {
    text = re.sub(r"([\(\[\{])\s+", r"\1", text)
    return text
