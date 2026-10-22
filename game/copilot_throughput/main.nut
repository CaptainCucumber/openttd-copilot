/* M1 throughput fixture. lifecycle.nut is staged beside this file by the harness. */
require("lifecycle.nut");

COPILOT_THROUGHPUT_TILES <- 10000;
COPILOT_THROUGHPUT_PIECES <- 100;
COPILOT_THROUGHPUT_CAP <- 20000;

class CopilotThroughput extends CopilotLifecycle {
	construction_id = null;
	construction_tiles = null;
	construction_track = null;
	construction_rail_type = null;
	construction_quote = null;
	construction_result = null;

	function _ObserveBenchmark(request)
	{
		local error = this._RequireWorld(request);
		if (error != null) return this._Error(request, error);
		foreach (key in ["start", "count"]) if (!(key in request)) return this._Error(request, "field_required");
		if (!this._IsInteger(request.start) || !this._IsInteger(request.count)) return this._Error(request, "invalid_field_type");
		if (request.count != COPILOT_THROUGHPUT_TILES || request.start < 0 || request.start >= GSMap.GetMapSize()) return this._Error(request, "invalid_observation_range");
		local started = GSController.GetTick();
		local observed = 0;
		local examined = 0;
		local owned = 0;
		local rail = 0;
		local water = 0;
		local buildable = 0;
		local checksum = 0;
		for (local tile = request.start; tile < GSMap.GetMapSize() && observed < request.count; tile++) {
			examined++;
			/* OpenTTD reserves a void border whose tile IDs are inside Map::Size(). */
			if (!GSMap.IsValidTile(tile)) continue;
			local row = this._TileState(tile);
			if (row.owner != GSCompany.COMPANY_INVALID) owned++;
			if (row.tracks != 0) rail++;
			if (GSTile.IsWaterTile(tile)) water++;
			if (GSTile.IsBuildable(tile)) buildable++;
			/* Bounded deterministic evidence that all five relevant row fields were read. */
			checksum = (checksum + (row.tile % 65521) + ((row.owner + 17) * 3) + (row.tracks * 5) + (row.slope * 7) + (row.height * 11)) % 2147483629;
			observed++;
		}
		if (observed != request.count) return this._Error(request, "insufficient_valid_tiles");
		local ended = GSController.GetTick();
		return this._Reply(request, true, {
			count = observed, examined = examined, start = request.start, start_tick = started, end_tick = ended,
			checksum = checksum, owned = owned, rail = rail, water = water, buildable = buildable
		});
	}

	function _PrepareConstruction(request)
	{
		local error = this._RequireBound(request);
		if (error != null) return this._Error(request, error);
		if (!("benchmark" in request) || !this._IsString(request.benchmark)) return this._Error(request, "invalid_benchmark");
		if (!("count" in request) || !this._IsInteger(request.count) || request.count != COPILOT_THROUGHPUT_PIECES) return this._Error(request, "invalid_piece_count");
		if (this.construction_id != null) {
			if (request.benchmark != this.construction_id) return this._Error(request, "benchmark_conflict");
			return this._Reply(request, true, { benchmark = this.construction_id, count = this.construction_tiles.len(), quote = this.construction_quote, duplicate = true });
		}
		local human = this._FindHuman();
		if (human == null || human.company != this.bound_company) return this._Error(request, "human_company_unavailable");
		local mode = GSCompanyMode(this.bound_company);
		local rail_type = this._AvailableRailType();
		if (rail_type == GSRail.RAILTYPE_INVALID) return this._Error(request, "no_rail_type");
		local tiles = [];
		local quote = 0;
		local map_size = GSMap.GetMapSize();
		local stride = 97;
		local tile = (GSMap.GetMapSizeY() / 4) * GSMap.GetMapSizeX();
		local attempts = 0;
		local legal = 0;
		local tested = 0;
		local positive = 0;
		local last_test_error = null;
		local max_attempts = map_size;
		GSRail.SetCurrentRailType(rail_type);
		while (tiles.len() < request.count && attempts < max_attempts) {
			tile = (tile + stride) % map_size;
			attempts++;
			if (!this._FlatLegal(tile) || GSRail.IsRailTile(tile)) continue;
			legal++;
			local ok = false;
			local cost = 0;
			{
				local test = GSTestMode();
				local accounting = GSAccounting();
				ok = GSRail.BuildRailTrack(tile, GSRail.RAILTRACK_NE_SW);
				cost = accounting.GetCosts();
			}
			if (!ok) { last_test_error = GSError.GetLastErrorString(); continue; }
			tested++;
			if (cost <= 0) continue;
			positive++;
			tiles.append(tile);
			quote += cost;
		}
		if (tiles.len() != request.count) return this._Reply(request, false, { error = "insufficient_candidates", attempts = attempts, legal = legal, tested = tested, positive = positive, found = tiles.len(), last_test_error = last_test_error, rail_type = rail_type, current_rail_type = GSRail.GetCurrentRailType(), rail_available = GSRail.IsRailTypeAvailable(rail_type) });
		local state = this._CompanyState(this.bound_company);
		if (quote > COPILOT_THROUGHPUT_CAP) return this._Error(request, "quote_over_fixture_cap");
		if (state.cash - quote < COPILOT_LIFECYCLE_RESERVE) return this._Error(request, "reserve");
		this.construction_id = request.benchmark;
		this.construction_tiles = tiles;
		this.construction_track = GSRail.RAILTRACK_NE_SW;
		this.construction_rail_type = rail_type;
		this.construction_quote = quote;
		return this._Reply(request, true, { benchmark = this.construction_id, count = tiles.len(), quote = quote, rail_type = rail_type, attempts = attempts });
	}

	function _ConstructionReply(request, result, duplicate = false)
	{
		local fields = { result = result, state = result.state, benchmark = result.benchmark, built = result.built, cost = result.cost, cash = result.cash, loan = result.loan, start_tick = result.start_tick, end_tick = result.end_tick };
		if (duplicate) fields.duplicate <- true;
		if (result.state != "completed") fields.error <- "partial_construction";
		return this._Reply(request, result.state == "completed", fields);
	}

	function _ConstructBenchmark(request)
	{
		local error = this._RequireBound(request);
		if (error != null) return this._Error(request, error);
		foreach (key in ["benchmark", "company", "cap"]) if (!(key in request)) return this._Error(request, "field_required");
		if (!this._IsString(request.benchmark) || !this._IsInteger(request.company) || !this._IsInteger(request.cap)) return this._Error(request, "invalid_field_type");
		if (this.construction_id == null || request.benchmark != this.construction_id || this.construction_tiles == null) return this._Error(request, "benchmark_not_prepared");
		if (request.company != this.bound_company) return this._Error(request, "company_mismatch");
		if (request.cap < 0 || request.cap > COPILOT_THROUGHPUT_CAP || this.construction_quote > request.cap) return this._Error(request, "cap");
		if (this.construction_result != null) return this._ConstructionReply(request, this.construction_result, true);
		if (GSGame.IsPaused()) return this._Error(request, "paused");
		local before = this._CompanyState(this.bound_company);
		if (before.cash - this.construction_quote < COPILOT_LIFECYCLE_RESERVE) return this._Error(request, "reserve");
		local started = GSController.GetTick();
		local built = 0;
		local cost = 0;
		local detail = null;
		local mode = GSCompanyMode(this.bound_company);
		GSRail.SetCurrentRailType(this.construction_rail_type);
		for (local i = 0; i < this.construction_tiles.len(); i++) {
			local tile = this.construction_tiles[i];
			local estimate = 0;
			local test_ok = false;
			{
				local test = GSTestMode();
				local accounting = GSAccounting();
				test_ok = GSRail.BuildRailTrack(tile, this.construction_track);
				estimate = accounting.GetCosts();
			}
			if (!test_ok || estimate < 0 || cost + estimate > request.cap) { detail = "precondition_" + i; break; }
			local ok = false;
			local piece_cost = 0;
			{
				local accounting = GSAccounting();
				ok = GSRail.BuildRailTrack(tile, this.construction_track);
				piece_cost = accounting.GetCosts();
			}
			cost += piece_cost;
			if (!ok || piece_cost != estimate || !GSRail.IsRailTile(tile) || GSTile.GetOwner(tile) != this.bound_company || !(GSRail.GetRailTracks(tile) & this.construction_track)) { detail = "mutation_" + i; break; }
			built++;
		}
		local after = this._CompanyState(this.bound_company);
		local ended = GSController.GetTick();
		local state = "completed";
		if (built != this.construction_tiles.len() || cost > request.cap || before.cash - after.cash != cost || before.loan != after.loan) state = "partial";
		this.construction_result = { state = state, benchmark = this.construction_id, built = built, requested = this.construction_tiles.len(), cost = cost, quote = this.construction_quote, cash = after.cash, loan = after.loan, start_tick = started, end_tick = ended, detail = detail };
		return this._ConstructionReply(request, this.construction_result);
	}

	function _ConstructionReadback(request)
	{
		local error = this._RequireWorld(request);
		if (error != null) return this._Error(request, error);
		if (!("benchmark" in request) || !this._IsString(request.benchmark) || request.benchmark != this.construction_id) return this._Error(request, "benchmark_not_found");
		local present = 0;
		local wrong_owner = 0;
		foreach (tile in this.construction_tiles) {
			if (GSRail.IsRailTile(tile) && (GSRail.GetRailTracks(tile) & this.construction_track)) present++;
			if (GSTile.GetOwner(tile) != this.bound_company) wrong_owner++;
		}
		return this._Reply(request, true, { benchmark = this.construction_id, requested = this.construction_tiles.len(), present = present, wrong_owner = wrong_owner });
	}

	function _Dispatch(request)
	{
		if (request == null || this._Type(request) != "table") return this._Error(null, "malformed");
		if (!("v" in request) || !this._IsInteger(request.v) || request.v != COPILOT_LIFECYCLE_VERSION) return this._Error(request, "unsupported_version");
		if (!("rid" in request) || !this._IsString(request.rid)) return this._Error(request, "invalid_rid");
		if (!("cmd" in request) || !this._IsString(request.cmd)) return this._Error(request, "invalid_command");
		if (request.cmd == "observe_benchmark") return this._ObserveBenchmark(request);
		if (request.cmd == "prepare_construction") return this._PrepareConstruction(request);
		if (request.cmd == "construct_benchmark") return this._ConstructBenchmark(request);
		if (request.cmd == "construction_readback") return this._ConstructionReadback(request);
		local parent_dispatch = CopilotLifecycle._Dispatch.bindenv(this);
		return parent_dispatch(request);
	}

	function Load(version, data)
	{
		local parent_load = CopilotLifecycle.Load.bindenv(this);
		parent_load(version, data);
		this.construction_id = null;
		this.construction_tiles = null;
		this.construction_track = null;
		this.construction_rail_type = null;
		this.construction_quote = null;
		this.construction_result = null;
	}
}
