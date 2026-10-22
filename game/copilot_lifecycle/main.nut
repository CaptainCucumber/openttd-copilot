/* S3a lifecycle fixture: a small versioned AdminPort/save-reload probe. */

COPILOT_LIFECYCLE_CLIENT <- "Copilot Probe Human";
COPILOT_LIFECYCLE_VERSION <- 1;
COPILOT_LIFECYCLE_MAX_ID <- 64;
COPILOT_LIFECYCLE_MAX_JOURNAL <- 32;
COPILOT_LIFECYCLE_MAX_CAP <- 10000;
COPILOT_LIFECYCLE_RESERVE <- 10000;
COPILOT_LIFECYCLE_MAX_CANDIDATES <- 96;

class CopilotLifecycle extends GSController {
	world = null;
	seq = 0;
	head = null;
	journal = [];
	pending = null;

	loaded = false;
	session = null;
	bound_company = GSCompany.COMPANY_INVALID;
	snapshot = null;

	function _Type(value) { return typeof(value); }
	function _IsInteger(value) { return this._Type(value) == "integer"; }
	function _IsString(value, allow_empty = false)
	{
		return this._Type(value) == "string" && (allow_empty || value.len() > 0) && value.len() <= COPILOT_LIFECYCLE_MAX_ID;
	}

	function _Escape(value)
	{
		local out = "\"";
		for (local i = 0; i < value.len(); i++) {
			local ch = value.slice(i, i + 1);
			if (ch == "\\") out = out + "\\\\";
			else if (ch == "\"") out = out + "\\\"";
			else if (ch == "\n") out = out + "\\n";
			else if (ch == "\r") out = out + "\\r";
			else if (ch == "\t") out = out + "\\t";
			else if (ch == "\b") out = out + "\\b";
			else if (ch == "\f") out = out + "\\f";
			else if (ch == "\x00") out = out + "\\u0000";
			else out = out + ch;
		}
		return out + "\"";
	}

	function _Json(value)
	{
		if (value == null) return "null";
		local kind = this._Type(value);
		if (kind == "string") return this._Escape(value);
		if (kind == "bool") return value ? "true" : "false";
		if (kind == "integer") return "" + value;
		if (kind == "float") return this._Escape("" + value);
		if (kind == "array") {
			local out = "[";
			local first = true;
			foreach (item in value) {
				if (!first) out = out + ",";
				first = false;
				out = out + this._Json(item);
			}
			return out + "]";
		}
		if (kind == "table") {
			local out = "{";
			local first = true;
			foreach (key, item in value) {
				if (!first) out = out + ",";
				first = false;
				out = out + this._Escape("" + key) + ":" + this._Json(item);
			}
			return out + "}";
		}
		return this._Escape("" + value);
	}

	function _LogError(message) { GSLog.Error("COPILOT_LIFECYCLE " + message); }

	function _Base(request, ok)
	{
		local rid = null;
		if (request != null && this._Type(request) == "table" && "rid" in request && this._IsString(request.rid)) rid = request.rid;
		return { v = COPILOT_LIFECYCLE_VERSION, rid = rid, ok = ok, world = this.world, seq = this.seq, head = this.head, tick = GSController.GetTick(), session = this.session };
	}

	function _Reply(request, ok, fields = null)
	{
		local reply = this._Base(request, ok);
		if (fields != null) foreach (key, value in fields) reply[key] <- value;
		if (this._Json(reply).len() >= 1450) {
			this._LogError("response_too_large");
			reply = this._Base(request, false);
			reply.error <- "response_too_large";
		}
		local sent = false;
		try { sent = GSAdmin.Send(reply); } catch (error) { this._LogError("send_exception " + error); }
		if (!sent) this._LogError("send_failed bytes=" + this._Json(reply).len());
		return sent;
	}

	function _Error(request, error) { return this._Reply(request, false, { error = error }); }

	function _FindHuman()
	{
		local clients = GSClientList();
		for (local id = clients.Begin(); !clients.IsEnd(); id = clients.Next()) {
			local name = GSClient.GetName(id);
			if (name != COPILOT_LIFECYCLE_CLIENT) continue;
			local company = GSCompany.ResolveCompanyID(GSClient.GetCompany(id));
			if (company != GSCompany.COMPANY_INVALID) return { client = id, company = company, name = name };
		}
		return null;
	}

	function _CompanyState(company)
	{
		local mode = GSCompanyMode(company);
		return { cash = GSCompany.GetBankBalance(company), loan = GSCompany.GetLoanAmount() };
	}

	function _TileState(tile)
	{
		local tracks = 0;
		if (GSRail.IsRailTile(tile)) tracks = GSRail.GetRailTracks(tile);
		return { tile = tile, owner = GSTile.GetOwner(tile), tracks = tracks, slope = GSTile.GetSlope(tile), height = GSTile.GetMinHeight(tile) };
	}

	function _Row(tile)
	{
		local state = this._TileState(tile);
		return [state.tile, state.owner, state.tracks, state.slope, state.height];
	}

	function _SamePayload(a, b)
	{
		if (a == null || b == null) return false;
		foreach (key in ["company", "tile", "track", "rail_type", "cap", "expect_seq"]) {
			if (!(key in a) || !(key in b) || a[key] != b[key]) return false;
		}
		return true;
	}

	function _JournalEntry(op)
	{
		foreach (entry in this.journal) if (entry.op == op) return entry;
		return null;
	}

	function _RequireWorld(request)
	{
		if (this.world == null) return "world_unset";
		if (!("world" in request) || !this._IsString(request.world)) return "world_required";
		if (request.world != this.world) return "world_mismatch";
		return null;
	}

	function _RequireBound(request)
	{
		local error = this._RequireWorld(request);
		if (error != null) return error;
		if (this.session == null || this.bound_company == GSCompany.COMPANY_INVALID) return "not_bound";
		if (!("session" in request) || !this._IsString(request.session) || request.session != this.session) return "session_mismatch";
		local human = this._FindHuman();
		if (human == null) return "human_company_unavailable";
		if (human.company != this.bound_company) return "company_changed";
		return null;
	}

	function _HumanReplyFields()
	{
		local fields = { human_found = false, map_width = GSMap.GetMapSizeX(), map_height = GSMap.GetMapSizeY() };
		local human = this._FindHuman();
		if (human == null) return fields;
		local mode = GSCompanyMode(human.company);
		local state = this._CompanyState(human.company);
		fields.human_found <- true;
		fields.client <- human.client;
		fields.client_name <- human.name;
		fields.company <- human.company;
		fields.company_name <- GSCompany.GetName(human.company);
		fields.cash <- state.cash;
		fields.loan <- state.loan;
		return fields;
	}

	function _AvailableRailType()
	{
		local rails = GSRailTypeList();
		for (local rail = rails.Begin(); !rails.IsEnd(); rail = rails.Next()) if (GSRail.IsRailTypeAvailable(rail)) return rail;
		return GSRail.RAILTYPE_INVALID;
	}

	function _FlatLegal(tile)
	{
		return GSMap.IsValidTile(tile) && !GSTile.IsWaterTile(tile) && GSTile.IsBuildable(tile) && GSTile.GetSlope(tile) == GSTile.SLOPE_FLAT;
	}

	function _Candidate(request)
	{
		local world_error = this._RequireWorld(request);
		if (world_error != null) return this._Error(request, world_error);
		local human = this._FindHuman();
		if (human == null) return this._Error(request, "human_company_unavailable");
		local mode = GSCompanyMode(human.company);
		local rail_type = this._AvailableRailType();
		if (rail_type == GSRail.RAILTYPE_INVALID) return this._Error(request, "no_rail_type");
		GSRail.SetCurrentRailType(rail_type);
		local width = GSMap.GetMapSizeX();
		local height = GSMap.GetMapSizeY();
		local cx = width / 2;
		local cy = height / 2;
		local tried = 0;
		for (local radius = 0; radius <= 24 && tried < COPILOT_LIFECYCLE_MAX_CANDIDATES; radius++) {
			for (local dy = -radius; dy <= radius && tried < COPILOT_LIFECYCLE_MAX_CANDIDATES; dy++) {
				for (local dx = -radius; dx <= radius && tried < COPILOT_LIFECYCLE_MAX_CANDIDATES; dx++) {
					if (radius != 0 && ((dx < 0 ? -dx : dx) != radius && (dy < 0 ? -dy : dy) != radius)) continue;
					local x = cx + dx;
					local y = cy + dy;
					if (x < 0 || y < 0 || x >= width || y >= height) continue;
					local tile = GSMap.GetTileIndex(x, y);
					tried++;
					if (!this._FlatLegal(tile)) continue;
					local before = this._CompanyState(human.company);
					local ok;
					local quote;
					{
						local test = GSTestMode();
						local accounting = GSAccounting();
						ok = GSRail.BuildRailTrack(tile, GSRail.RAILTRACK_NE_SW);
						quote = accounting.GetCosts();
					}
					local after = this._CompanyState(human.company);
					if (!ok || quote < 0 || before.cash != after.cash || before.loan != after.loan || GSRail.IsRailTile(tile)) continue;
					return this._Reply(request, true, { company = human.company, tile = tile, track = GSRail.RAILTRACK_NE_SW, rail_type = rail_type, quote = quote, candidate = { tile = tile, track = GSRail.RAILTRACK_NE_SW, rail_type = rail_type, quote = quote } });
				}
			}
		}
		return this._Error(request, "no_candidate");
	}

	function _BuildOutcome(tile, state, cost, cash, loan, op = null)
	{
		local row = this._TileState(tile);
		return { state = state, op = op, cost = cost, cash = cash, loan = loan, tile = tile, owner = row.owner, tracks = row.tracks, seq = this.seq };
	}

	function _OutcomeReply(request, outcome, duplicate = false, reason = null)
	{
		local fields = { outcome = outcome, state = outcome.state, cost = outcome.cost, cash = outcome.cash, loan = outcome.loan, tile = outcome.tile, owner = outcome.owner, tracks = outcome.tracks };
		if (duplicate) fields.duplicate <- true;
		if (reason != null) fields.reason <- reason;
		return this._Reply(request, true, fields);
	}

	function _Build(request)
	{
		local error = this._RequireBound(request);
		if (error != null) return this._Error(request, error);
		foreach (key in ["op", "company", "tile", "track", "rail_type", "cap", "expect_seq"]) if (!(key in request)) return this._Error(request, "field_required");
		if (!this._IsString(request.op)) return this._Error(request, "invalid_op");
		foreach (key in ["company", "tile", "track", "rail_type", "cap", "expect_seq"]) if (!this._IsInteger(request[key])) return this._Error(request, "invalid_field_type");
		local payload = { company = request.company, tile = request.tile, track = request.track, rail_type = request.rail_type, cap = request.cap, expect_seq = request.expect_seq };
		local existing = this._JournalEntry(request.op);
		if (existing != null) {
			if (!this._SamePayload(existing.payload, payload)) return this._Error(request, "id_conflict");
			return this._OutcomeReply(request, existing.outcome, true);
		}
		if (request.company != this.bound_company) return this._Error(request, "company_mismatch");
		if (request.tile < 0 || !GSMap.IsValidTile(request.tile)) return this._Error(request, "invalid_tile");
		if (!this._FlatLegal(request.tile)) return this._Error(request, "invalid_tile");
		if (request.track != GSRail.RAILTRACK_NE_SW) return this._Error(request, "invalid_track");
		if (request.rail_type < 0 || !GSRail.IsRailTypeAvailable(request.rail_type)) return this._Error(request, "invalid_rail_type");
		if (request.cap < 0 || request.cap > COPILOT_LIFECYCLE_MAX_CAP) return this._Error(request, "invalid_cap");
		if (request.expect_seq < 0 || request.expect_seq != this.seq) return this._Error(request, "seq_mismatch");
		if (this.pending != null) {
			if (!("op" in this.pending) || this.pending.op != request.op) return this._Error(request, "uncertain_pending");
			if ("payload" in this.pending && !this._SamePayload(this.pending.payload, payload)) return this._Error(request, "id_conflict");
			return this._Error(request, "uncertain_pending");
		}
		if (this.journal.len() >= COPILOT_LIFECYCLE_MAX_JOURNAL) return this._Error(request, "journal_full");
		if (GSGame.IsPaused()) return this._Error(request, "paused");

		local mode = GSCompanyMode(this.bound_company);
		GSRail.SetCurrentRailType(request.rail_type);
		local before = this._CompanyState(this.bound_company);
		local test_ok;
		local estimate;
		try {
			local test = GSTestMode();
			local accounting = GSAccounting();
			test_ok = GSRail.BuildRailTrack(request.tile, request.track);
			estimate = accounting.GetCosts();
		} catch (error) {
			return this._Error(request, "command_test_exception");
		}
		if (!test_ok) {
			local outcome = this._BuildOutcome(request.tile, "rejected", 0, before.cash, before.loan, request.op);
			this.journal.append({ op = request.op, payload = payload, outcome = outcome });
			return this._OutcomeReply(request, outcome);
		}
		if (estimate < 0 || estimate > request.cap) {
			local outcome = this._BuildOutcome(request.tile, "rejected", 0, before.cash, before.loan, request.op);
			this.journal.append({ op = request.op, payload = payload, outcome = outcome });
			return this._OutcomeReply(request, outcome, false, "cap");
		}
		if (before.cash - estimate < COPILOT_LIFECYCLE_RESERVE || before.loan != GSCompany.GetLoanAmount()) {
			local outcome = this._BuildOutcome(request.tile, "rejected", 0, before.cash, before.loan, request.op);
			this.journal.append({ op = request.op, payload = payload, outcome = outcome });
			return this._OutcomeReply(request, outcome, false, "reserve");
		}

		this.pending = { op = request.op, payload = payload, started_tick = GSController.GetTick() };
		try {
			local accounting = GSAccounting();
			local ok = GSRail.BuildRailTrack(request.tile, request.track);
			local cost = accounting.GetCosts();
			local after = this._CompanyState(this.bound_company);
			local row = this._TileState(request.tile);
			if (!ok) {
				local outcome = this._BuildOutcome(request.tile, "rejected", cost, after.cash, after.loan, request.op);
				this.journal.append({ op = request.op, payload = payload, outcome = outcome });
				this.pending = null;
				return this._OutcomeReply(request, outcome);
			}
			if (cost > request.cap || before.cash - after.cash != cost || before.loan != after.loan || row.owner != this.bound_company || row.tracks != request.track) {
				local outcome = this._BuildOutcome(request.tile, "uncertain", cost, after.cash, after.loan, request.op);
				this.pending.outcome <- outcome;
				return this._Reply(request, false, { error = "uncertain", outcome = outcome, state = outcome.state, cost = outcome.cost, cash = outcome.cash, loan = outcome.loan, tile = outcome.tile, owner = outcome.owner, tracks = outcome.tracks, seq = outcome.seq });
			}
			this.seq++;
			this.head = request.op;
			local outcome = this._BuildOutcome(request.tile, "completed", cost, after.cash, after.loan, request.op);
			outcome.seq = this.seq;
			this.journal.append({ op = request.op, payload = payload, outcome = outcome });
			this.pending = null;
			return this._OutcomeReply(request, outcome);
		} catch (error) {
			this._LogError("build_exception op=" + request.op + " detail=" + error);
			local after = this._CompanyState(this.bound_company);
			local outcome = this._BuildOutcome(request.tile, "uncertain", 0, after.cash, after.loan, request.op);
			this.pending.outcome <- outcome;
			return this._Reply(request, false, { error = "uncertain", outcome = outcome, state = outcome.state, cost = outcome.cost, cash = outcome.cash, loan = outcome.loan, tile = outcome.tile, owner = outcome.owner, tracks = outcome.tracks, seq = outcome.seq });
		}
	}

	function _Hello(request)
	{
		local fields = this._HumanReplyFields();
		fields.loaded <- this.loaded;
		fields.paused <- GSGame.IsPaused();
		fields.date <- GSDate.GetCurrentDate();
		return this._Reply(request, true, fields);
	}

	function _Init(request)
	{
		if (!("world" in request) || !this._IsString(request.world)) return this._Error(request, "invalid_world");
		if (this.world != null && this.world != request.world) return this._Error(request, "world_mismatch");
		local initialized = this.world == null;
		if (initialized) this.world = request.world;
		return this._Reply(request, true, { initialized = initialized });
	}

	function _Bind(request)
	{
		local error = this._RequireWorld(request);
		if (error != null) return this._Error(request, error);
		if (!("session" in request) || !this._IsString(request.session)) return this._Error(request, "invalid_session");
		local human = this._FindHuman();
		if (human == null) return this._Error(request, "human_company_unavailable");
		this.session = request.session;
		this.bound_company = human.company;
		return this._Reply(request, true, { bound = true, company = this.bound_company, client = human.client });
	}

	function _Status(request)
	{
		local error = this._RequireWorld(request);
		if (error != null) return this._Error(request, error);
		if (!("op" in request) || !this._IsString(request.op)) return this._Error(request, "invalid_op");
		local entry = this._JournalEntry(request.op);
		if (entry == null) {
		if (this.pending != null && "op" in this.pending && this.pending.op == request.op) {
				local uncertain = ("outcome" in this.pending) ? this.pending.outcome : { state = "uncertain", op = this.pending.op, cost = null, cash = null, loan = null, tile = this.pending.payload.tile, owner = null, tracks = null, seq = this.seq };
				return this._Reply(request, true, { state = "uncertain", outcome = uncertain });
			}
			return this._Reply(request, true, { state = "unknown", outcome = { state = "unknown", op = request.op, cost = null, cash = null, loan = null, tile = null, owner = null, tracks = null, seq = this.seq } });
		}
		return this._Reply(request, true, { state = entry.outcome.state, outcome = entry.outcome, op = entry.op });
	}

	function _Scan(request)
	{
		local error = this._RequireWorld(request);
		if (error != null) return this._Error(request, error);
		foreach (key in ["scan", "start", "count"]) if (!(key in request)) return this._Error(request, "field_required");
		if (!this._IsString(request.scan)) return this._Error(request, "invalid_scan");
		if (!this._IsInteger(request.start) || !this._IsInteger(request.count)) return this._Error(request, "invalid_field_type");
		if (request.count < 1 || request.count > 32 || request.start < 0 || !GSMap.IsValidTile(request.start) || request.start + request.count > GSMap.GetMapSize()) return this._Error(request, "invalid_scan_range");
		for (local check = 0; check < request.count; check++) if (!GSMap.IsValidTile(request.start + check)) return this._Error(request, "invalid_scan_range");
		if (this.snapshot != null && this.snapshot.scan == request.scan) {
			if (this.snapshot.start != request.start || this.snapshot.count != request.count) return this._Error(request, "id_conflict");
			return this._Reply(request, true, { scan = this.snapshot.scan, total = this.snapshot.count, pages = this.snapshot.pages, start_tick = this.snapshot.started_tick, end_tick = this.snapshot.ended_tick, capture_start_tick = this.snapshot.started_tick, capture_end_tick = this.snapshot.ended_tick, duplicate = true });
		}
		local started = GSController.GetTick();
		local rows = [];
		for (local i = 0; i < request.count; i++) rows.append(this._Row(request.start + i));
		local ended = GSController.GetTick();
		this.snapshot = { scan = request.scan, rows = rows, start = request.start, count = request.count, started_tick = started, ended_tick = ended, pages = (request.count + 3) / 4 };
		return this._Reply(request, true, { scan = request.scan, total = request.count, pages = this.snapshot.pages, start_tick = started, end_tick = ended, capture_start_tick = started, capture_end_tick = ended });
	}

	function _Page(request)
	{
		local error = this._RequireWorld(request);
		if (error != null) return this._Error(request, error);
		if (!("scan" in request) || !("index" in request)) return this._Error(request, "field_required");
		if (!this._IsString(request.scan) || !this._IsInteger(request.index)) return this._Error(request, "invalid_field_type");
		if (this.snapshot == null || this.snapshot.scan != request.scan) return this._Error(request, "scan_not_found");
		if (request.index < 0 || request.index >= this.snapshot.pages) return this._Error(request, "invalid_page");
		local rows = [];
		local first = request.index * 4;
		local last = first + 4;
		if (last > this.snapshot.rows.len()) last = this.snapshot.rows.len();
		for (local i = first; i < last; i++) rows.append(this.snapshot.rows[i]);
		return this._Reply(request, true, { scan = this.snapshot.scan, index = request.index, rows = rows, total = this.snapshot.count, pages = this.snapshot.pages, start_tick = this.snapshot.started_tick, end_tick = this.snapshot.ended_tick, capture_start_tick = this.snapshot.started_tick, capture_end_tick = this.snapshot.ended_tick });
	}

	function _Dispatch(request)
	{
		if (request == null || this._Type(request) != "table") return this._Error(null, "malformed");
		if (!("v" in request) || !this._IsInteger(request.v) || request.v != COPILOT_LIFECYCLE_VERSION) return this._Error(request, "unsupported_version");
		if (!("rid" in request) || !this._IsString(request.rid)) return this._Error(request, "invalid_rid");
		if (!("cmd" in request) || !this._IsString(request.cmd)) return this._Error(request, "invalid_command");
		if (request.cmd == "hello") return this._Hello(request);
		if (request.cmd == "init") return this._Init(request);
		if (request.cmd == "bind") return this._Bind(request);
		if (request.cmd == "candidate") return this._Candidate(request);
		if (request.cmd == "build") return this._Build(request);
		if (request.cmd == "status") return this._Status(request);
		if (request.cmd == "scan") return this._Scan(request);
		if (request.cmd == "page") return this._Page(request);
		return this._Error(request, "unknown_command");
	}

	function Start()
	{
		this.session = null;
		this.bound_company = GSCompany.COMPANY_INVALID;
		this.snapshot = null;
		GSLog.Info("COPILOT_LIFECYCLE startup loaded=" + (this.loaded ? "true" : "false") + " world=" + (this.world == null ? "null" : this.world) + " seq=" + this.seq + " head=" + (this.head == null ? "null" : this.head));
		while (true) {
			if (!GSEventController.IsEventWaiting()) { GSController.Sleep(1); continue; }
			local event = GSEventController.GetNextEvent();
			try {
				if (event != null && event.GetEventType() == GSEvent.ET_ADMIN_PORT) {
					local admin = GSEventAdminPort.Convert(event);
					local request = admin.GetObject();
					try {
						this._Dispatch(request);
					} catch (dispatch_error) {
						this._LogError("dispatch_exception " + dispatch_error);
						this._Error(request, "internal_error");
					}
				}
			} catch (error) { this._LogError("event_exception " + error); }
		}
	}

	function Save()
	{
		return { protocol = 1, world = this.world, seq = this.seq, head = this.head, journal = this.journal, pending = this.pending };
	}

	function Load(version, data)
	{
		this.loaded = true;
		this.world = (data != null && "world" in data) ? data.world : null;
		this.seq = (data != null && "seq" in data && this._IsInteger(data.seq)) ? data.seq : 0;
		this.head = (data != null && "head" in data) ? data.head : null;
		this.journal = (data != null && "journal" in data && this._Type(data.journal) == "array") ? data.journal : [];
		this.pending = (data != null && "pending" in data) ? data.pending : null;
		this.session = null;
		this.bound_company = GSCompany.COMPANY_INVALID;
		this.snapshot = null;
	}
}
