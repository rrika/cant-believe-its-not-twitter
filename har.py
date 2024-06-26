import os, os.path, json, io, hashlib, base64, gzip, re
try: import brotli
except: print("warning: brotli-compressed data in warcs can't be decoded without brotli module")

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

class InWarc:
	def __init__(self, f, offset, size, mode="rb", encoding=None, chunked=False):
		self.f = f
		self.offset = offset
		self.size = size
		self.mode = mode
		self.encoding = encoding
		self.chunked = chunked
		assert mode in ("r", "rb")

	def open(self):
		if self.chunked:
			raise Exception("chunking not supported")
		self.f.seek(self.offset)
		data = self.f.read(self.size)
		if self.encoding == "gzip":
			data = gzip.decompress(data)
		elif self.encoding == "br":
			data = brotli.decompress(data)
		if self.mode == "r":
			return io.BytesIO(data)
		else:
			return io.StringIO(data.decode("utf-8"))

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

header_re = re.compile(rb"(.*): (.*)\r\n")

def parse_warc(f, size=None):
	"yields (headers, offset, length)"

	if size is None:
		size = os.fstat(f.fileno()).st_size
	while line := f.readline():
		assert line == b"WARC/1.0\r\n", line

		# read headers until blank line
		headers = []
		length = None
		while True:
			header_line = f.readline()
			if header_line == b"\r\n": break
			m = header_re.match(header_line)
			name = m.group(1)
			value = m.group(2)
			headers.append((name, value))
			if name.lower() == b"content-length":
				length = int(value)

		# skip content bytes
		offset = f.tell()
		yield (headers, offset, length)
		f.seek(offset + length)

		# expect two blank lines
		line = f.readline()
		assert line == b"\r\n", line
		line = f.readline()
		assert line == b"\r\n", line

def read_header_lines_limited(f, stop):
	offset = f.tell()
	while True:
		line = f.readline()
		if line == b"\r\n": # early stop on empty line
			break
		xo = offset + len(line)
		if xo > stop:
			yield line[:stop-offset]
			break
		elif xo <= stop:
			yield line
			if xo == stop:
				break
		offset = xo

def read_warc(f, size=None, responses=None):
	if responses is None:
		responses = {}
	order = []
	for headers, offset, length in parse_warc(f, size):
		h = {name.lower(): value for name, value in headers}
		warc_type = h[b"warc-type"]
		if warc_type == b"warcinfo":
			continue
		warc_record_id = h[b"warc-record-id"]
		warc_date = h[b"warc-date"]
		warc_target_uri = h[b"warc-target-uri"]
		keep_headers = {
			"warc-date": warc_date.decode("utf-8"),
			"warc-target-uri": warc_target_uri.decode("utf-8"),
		}
		if warc_type == b"response":
			response_headers = list(read_header_lines_limited(f, stop=offset+length))
			payload_begin = f.tell()
			encoding = None
			mime = None
			for h in response_headers:
				if h.lower().startswith(b"content-encoding: "):
					encoding = h[18:-2].decode("ascii") # HACK
				if h.lower().startswith(b"content-type: "):
					mime = h[14:-2].decode("ascii") # HACK
			chunked = b"transfer-encoding: chunked\r\n" in response_headers
			payload = InWarc(f, payload_begin, offset + length - payload_begin, mode="r",
				encoding=encoding, chunked=chunked)
			if mime:
				payload.mime = mime
			assert warc_record_id not in responses
			responses[warc_record_id] = [None, (keep_headers, response_headers, payload)]
			order.append(warc_record_id)

		elif warc_type == b"revisit":
			response_headers = list(read_header_lines_limited(f, stop=offset+length))
			warc_refers_to = h.get(b"warc-refers-to", None)
			payload = responses[warc_refers_to][1][2]
			assert warc_record_id not in responses
			responses[warc_record_id] = [None, (keep_headers, response_headers, payload)]
			order.append(warc_record_id)

		elif warc_type == b"request":
			request_headers = list(read_header_lines_limited(f, stop=offset+length))
			warc_concurrent_to = [value for name, value in headers if name.lower() == b"warc-concurrent-to"]
			for response_record_id in warc_concurrent_to:
				assert responses[response_record_id][0] == None
				responses[response_record_id][0] = (keep_headers, request_headers)

	return [responses[record_id] for record_id in order]
