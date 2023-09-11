# This code is to merge different observations of a list of items into a single
# history of the whole list. An assumption is that the observations are always
# ordered by addition time. Removal and subsequent addition moves an item back
# to the top. This code supports observations that only identify the items, as
# well as such which identify the item and the addition event.
#
# Concretely, Twitter archive zips contain a list of likes that span about a
# year into the past. Those only identify the tweets.
# API interactions on the other hand provide both a tweet and a like id.

class Items:
	def __init__(self, items):
		self.items = items
	def __len__(self):
		return len(self.items)

class Events:
	def __init__(self, seq):
		self.seq = seq
	def __len__(self):
		return len(self.seq)

def align(
	snapshots,
	evid_lower_bound_for_itid=None,
	allow_retcon=True
):
	print = lambda *args: None

	current_seq = []
	recognized = {}
	edges = {}
	ver = {}
	def newver(itid):
		v = ver.get(itid, 0)
		ver[itid] = v-1
		return v

	seqs = []

	for si, snapshot in enumerate(snapshots): # from most recent to oldest
		prev_seq = current_seq
		index = {itid: (i, evid) for i, (itid, evid) in enumerate(prev_seq)}
		print()
		print(snapshot, len(prev_seq))

		if isinstance(snapshot, Items):
			if len(prev_seq) == 0:
				current_seq = [(itid, newver(itid)) for itid in snapshot.items]
			else:
				matching = []
				ri = None
				for j, itid in enumerate(snapshot.items):
					i, evid = index.get(itid, (None, None))
					if i is not None:
						if ri is not None:
							if i < ri:
								continue
							elif ri+1 < i and not allow_retcon:
								matching = []
						matching.append(j)
						ri = i

				current_seq = []
				for j, itid in enumerate(snapshot.items):
					i, evid = index.get(itid, (None, 0))
					if evid <= 0 and j not in matching:
						current_seq.append((itid, newver(itid)))
					else:
						current_seq.append((itid, evid))

				if 0 not in matching:
					if matching:
						fi = index[snapshot.items[matching[0]]][0]
					else:
						print("insert below")
						fi = len(prev_seq)
						ri = len(prev_seq)
					if fi > 0:
						edges.setdefault(prev_seq[fi-1], []).append(current_seq[0])

				assert ri is not None, "figure out what to do in this case"
				current_seq += prev_seq[ri+1:]

		if isinstance(snapshot, Events) and not prev_seq:
			current_seq = [(itid, evid) for evid, itid in snapshot.seq]
			for j, (evid, itid) in enumerate(snapshot.seq):
				i, revid = index.get(itid, (None, None))
				print((itid, revid, evid))

		if isinstance(snapshot, Events) and prev_seq:
			current_seq = [(itid, evid) for evid, itid in snapshot.seq]
			assert sorted(current_seq, key=lambda ie: -ie[1]) == current_seq
			matching = []
			fi = None
			ri = None
			for j, (evid, itid) in enumerate(snapshot.seq):
				i, revid = index.get(itid, (None, None))
				print((itid, revid, evid))
				if i is None:
					continue
				if fi is None:
					fi = i
				if ri is not None:
					if i < ri:
						continue
					elif i > ri+1 and not allow_retcon:
						print(evid, itid, ri, i)
						assert False
						fi = i
						matching = []
				ri = i
				matching.append(j)

			for j, (evid, itid) in enumerate(snapshot.seq):
				i, revid = index.get(itid, (None, 1))
				if revid <= 0 and j in matching:
					recognized[itid, revid] = evid
				#elif revid <= 0:
				#	e = edges.setdefault((itid, revid), []).append(snapshot.seq[0][::-1])

			if not matching:
				assert fi is None
				assert ri is None
				pfev = None
				plev = None
				top = snapshot.seq[0][0]
				bot = snapshot.seq[-1][0]
				print("top bot", top, bot)
				for _, pevid in prev_seq:
					if pevid is not None:
						if pevid > top: pfev = pevid or pfev
						if pevid < bot: plev = plev or plev
				print("pfev plev", pfev, plev)
				if pfev is None:
					print("insert above")
					fi = 0
					ri = -1
				elif plev is None:
					print("insert below")
					fi = len(prev_seq)
					ri = len(prev_seq)-1

			if 0 not in matching:
				assert current_seq[0] == snapshot.seq[0][::-1]
				if matching:
					assert fi == index[snapshot.seq[matching[0]][1]][0]
				if fi > 0:
					edges.setdefault(prev_seq[fi-1], []).append(snapshot.seq[0][::-1])

			if fi is not None:
				current_seq = prev_seq[:fi] + current_seq + prev_seq[ri+1:]

		#print(current_seq)
		seqs.append(current_seq)

	print("edges", edges)
	print("recognized", recognized)
	pevid = 0
	for seq in reversed(seqs):
		for itid, evid in reversed(seq):
			if evid <= 0:
				evid = recognized.get((itid, evid), evid)
			if evid <= 0:
				m = []
				if pevid is not None:
					m.append(pevid)
				if (itid, evid-1) in recognized:
					m.append(recognized[itid, evid-1])
				for (xitid, xevid) in edges.get((itid, evid), []):
					if xevid <= 0:
						xevid = recognized.get((xitid, xevid), xevid)
					if xevid <= 0:
						assert False, (xitid, xevid)
					else:
						m.append(xevid)
				if evid_lower_bound_for_itid:
					m.append(evid_lower_bound_for_itid(itid))
				if len(m):
					pevid = recognized[itid, evid] = max(m)+1
					evid = pevid
			else:
				pevid = evid
		pevid = None
	print("recognized", recognized)
	# find the last event for each item
	evmap = {}
	for seq in reversed(seqs):
		for itid, evid in seq:
			if evid <= 0:
				evid = recognized.get((itid, evid))
			if evid <= 0:
				assert False, itid
			evmap[itid] = evid
	items = []
	for itid, evid in evmap.items():
		items.append((evid, itid))
	items.sort(key=lambda ei: -ei[0])
	print(items)
	print()
	return items

if __name__ == '__main__':
	s0 = Items(list("ECBD"))
	s1 = Items(list("CB"))
	s2 = Items(list("DCBA"))
	r = align([s0, s1, s2])
	assert r == [(7, 'E'), (6, 'C'), (5, 'B'), (4, 'D'), (1, 'A')], r

	s0 = Items(list("ECBA"))
	s1 = Events([(80, "D"), (70, "C")])
	r = align([s0, s1])
	assert r == [(81, 'E'), (80, 'D'), (70, 'C'), (2, 'B'), (1, 'A')], r

	# s0 = Items(list("ECBA"))
	# s1 = Events([(80, "D"), (70, "C"), (60, "A")])
	# r = align([s0, s1])
	# assert r == [(83, 'E'), (82, 'C'), (81, 'B'), (80, 'D'), (60, 'A')]

	s0 = Items(list("ECBA"))
	s1 = Items(list("DCA"))
	r = align([s0, s1], allow_retcon=False)
	assert r == [(6, 'E'), (5, 'C'), (4, 'B'), (3, 'D'), (1, 'A')], r
