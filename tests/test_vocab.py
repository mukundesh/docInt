# Vocab is built from 'The quick brown fox jumped over the LAZY Fox.'


def test_vocab_insensitive(insensitive_vocab):
    vocab = insensitive_vocab

    assert "the" in vocab
    assert "The" in vocab
    assert "quick" in vocab
    assert "Quick" in vocab
    assert "BROWN" in vocab
    assert "BROW" not in vocab
    assert "fox." not in vocab


def test_vocab_sensitive(sensitive_vocab):
    vocab = sensitive_vocab

    assert "The" in vocab
    assert "the" in vocab

    assert "LAZY" in vocab
    assert "lazy" not in vocab

    assert "Fox" in vocab
    assert "fox." not in vocab

    assert "brow" not in vocab
    assert "Fo" not in vocab

    assert "" not in vocab


def test_has_text(insensitive_vocab):
    vocab = insensitive_vocab
    assert vocab.has_text("brown", dist_cutoff=1)
    assert vocab.has_text("bromn", dist_cutoff=1)

    assert not vocab.has_text("cromn", dist_cutoff=1)
    assert vocab.has_text("cromn", dist_cutoff=2)

    assert vocab.has_text("brow", dist_cutoff=2)


def test_find_texts(sensitive_vocab):
    vocab = sensitive_vocab

    assert len(vocab.find_texts("the", dist_cutoff=0)) == 1
    assert len(vocab.find_texts("the", dist_cutoff=1)) == 2
