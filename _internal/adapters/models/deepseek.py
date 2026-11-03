class DeepSeekClient:
    def __init__(self, key, model, request):
        self.key, self.model, self.request = key, model, request

    def complete(self, prompt, max_tokens=8192):
        return self.request(self.key, self.model, prompt, max_tokens)
