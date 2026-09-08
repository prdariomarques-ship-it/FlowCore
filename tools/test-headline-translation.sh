#!/bin/bash
# Test headline translation on z3 (requires Ollama or DeepSeek configured)

set -e

echo "FlowCore Headline Translation Test"
echo "==================================="
echo ""

cd ~/FlowCore 2>/dev/null || cd "$(dirname "$0")/.."

echo "1. Checking ai.json configuration..."
if [ -f ~/.flowcore/ai.json ]; then
    echo "   ✅ ai.json found"
    python3 -c "
import json
with open(str(Path.home() / '.flowcore' / 'ai.json')) as f:
    cfg = json.load(f)
    print('   Configured providers:')
    if cfg.get('deepseek_url'):
        print(f'   - DeepSeek: {cfg[\"deepseek_url\"]}')
    if cfg.get('ollama_url'):
        print(f'   - Ollama: {cfg[\"ollama_url\"]}')
    if cfg.get('openai_url'):
        print(f'   - OpenAI: {cfg[\"openai_url\"]}')
" 2>/dev/null || echo "   (unable to parse config)"
else
    echo "   ⚠️  ai.json not found — translations will return English"
fi
echo ""

echo "2. Testing translation function..."
python3 << 'EOF'
import sys
sys.path.insert(0, "/root/FlowCore")

from runtime.market_intelligence.news import _translate_to_portuguese

test_headlines = [
    "S&P 500 closes at record high",
    "Brazil's central bank signals rate cut",
    "Tesla rises on earnings beat",
]

for headline in test_headlines:
    translated = _translate_to_portuguese(headline)
    # Mark if it actually translated (different from input)
    is_translated = "✨" if translated != headline else "  "
    print(f"   {is_translated} EN: {headline}")
    print(f"      PT: {translated}")
    print()
EOF

echo "==================================="
echo "✅ Translation test complete"
echo ""
echo "If headlines are in Portuguese (✨), LLM translation is working!"
echo "If they're still in English, LLM is not available — that's OK, feeds degrade gracefully."
