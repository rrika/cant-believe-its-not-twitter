import os, os.path, json, io, hashlib, base64

class OnDisk:
	def __init__(self, path, mode="rb"):
		self.path = path
		self.mode = mode

	def open(self):
		return open(self.path, self.mode)

class InZip:
	def __init__(self, zipf, path):
		self.zipf = zipf
		self.path = path

	def open(self):
		return self.zipf.open(self.path)

class InMemory:
	def __init__(self, data):
		self.data = data

	def open(self):
		data = self.data
		if isinstance(data, str):
			return io.StringIO(data)
		elif isinstance(data, bytes):
			return io.BytesIO(data)


class HarStore:
	def __init__(self, path):
		self.path = path = path.rstrip("/")
		assert path
		os.makedirs(path + "/blob", exist_ok=True)
		os.makedirs(path + "/lhar", exist_ok=True)

	def load(self, har_path):		
		lhar_path = self.path + "/lhar/" + os.path.basename(har_path)

		if os.path.exists(lhar_path):
			with open(lhar_path) as f:
				lhar = json.load(f)
			return lhar

		else:
			with open(har_path) as f:
				har = json.load(f)
			return har

	def get_har_entry_data(self, entry):
		content = entry.get("response", {}).get("content", {})
		if "text" not in content:
			return None
		data = content["text"]
		if content.get("encoding", None) == "base64":
			data = base64.b64decode(data)
		return data

	def does_lhar_entry_have_data(self, entry):
		content = entry.get("response", {}).get("content", {})
		if "hashtxt" in content or "hashbin" in content or "text" in content:
			return True

	def get_lhar_entry(self, entry):
		content = entry.get("response", {}).get("content", None)
		if "hashtxt" in content:
			e = OnDisk(self.path + "/blob/" + content["hashtxt"], "r")
		elif "hashbin" in content:
			e = OnDisk(self.path + "/blob/" + content["hashbin"], "rb")
		elif "text" in content:
			e = InMemory(self.get_har_entry_data(entry))
		else:
			return None
		e.mime = content.get("mimeType", None)
		return e

	def should_offload(self, entry):
		content = entry.get("response", {}).get("content", None)
		if not content:
			return False
		if "text" not in content:
			return False
		if content.get("encoding", None) == "base64":
			return True
		if content.get("size") >= 2 * 1024 * 1024:
			return True
		return False

	def add(self, har_path, skip_if_exists=False):
		lhar_path = self.path + "/lhar/" + os.path.basename(har_path)
		if skip_if_exists and os.path.exists(lhar_path):
			return

		with open(har_path) as f:
			har = json.load(f)
		entries = har.get("log", {}).get("entries", [])
		for entry in entries:
			if self.should_offload(entry):
				try:
					data = self.get_har_entry_data(entry)
				except ValueError:
					# firefox sometimes declares base64 wrongly
					continue
				content = entry["response"]["content"]
				content.pop("text")
				content.pop("encoding", None)
				text = isinstance(data, str)
				if text:
					data = data.encode("utf-8")
				h = hashlib.sha1(data).hexdigest()
				with open(self.path + "/blob/" + h, "wb") as f:
					f.write(data)
				if text:
					content["hashtxt"] = h
				else:
					content["hashbin"] = h

		with open(lhar_path, "w") as f:
			json.dump(har, f, indent=2)
