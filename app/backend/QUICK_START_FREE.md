# 🚀 Quick Start: Use FREE Embeddings (No API Key!)

## ✅ Solution: Use Hugging Face (FREE)

You can use **FREE embeddings** that don't require any API key or quota!

### Step 1: Install Required Package (One-time)

```bash
cd app/backend
source venv/bin/activate  # Activate virtual environment
pip install sentence-transformers
```

### Step 2: Set Provider to Hugging Face

```bash
export EMBEDDING_PROVIDER=huggingface
```

Or add to `.env` file:
```
EMBEDDING_PROVIDER=huggingface
```

### Step 3: Run Ingestion

```bash
python ingest_documents.py
```

**That's it!** No API key needed, no quota limits! 🎉

## 🎯 Alternative: FastEmbed (Also FREE)

If you prefer FastEmbed (already installed):

```bash
export EMBEDDING_PROVIDER=fastembed
python ingest_documents.py
```

## 📝 Summary

- ✅ **Hugging Face**: FREE, no API key, good quality
- ✅ **FastEmbed**: FREE, no API key, very fast
- ❌ **OpenAI**: Paid, requires API key with quota

**Recommendation:** Use Hugging Face for free, unlimited embeddings!

