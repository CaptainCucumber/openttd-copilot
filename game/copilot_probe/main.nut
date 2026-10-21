/*
 * S2 control probe.  This is intentionally a fixture, not a route planner or
 * production adapter.  It operates only in the company belonging to the
 * explicitly named connected client and never changes a loan or gives money.
 */

COPILOT_CLIENT_NAME <- "Copilot Probe Human";
COPILOT_SPEND_CAP <- 10000;
COPILOT_CASH_RESERVE <- 10000;
COPILOT_MAX_CLIENT_WAITS <- 120;
COPILOT_MAX_CANDIDATES <- 96;

class CopilotProbe extends GSController {

	started = false;
	loaded = false;
	state = "created";
	result = null;
	progress = null;
	saved = null;
	company = GSCompany.COMPANY_INVALID;
	client = GSClient.CLIENT_INVALID;
	coal = -1;
	producer = -1;
	acceptor = -1;
	chosen_rail = GSRail.RAILTYPE_INVALID;
	candidate = null;

	function _EscapeString(value)
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
			else if (ch == "\x01") out = out + "\\u0001";
			else if (ch == "\x02") out = out + "\\u0002";
			else if (ch == "\x03") out = out + "\\u0003";
			else if (ch == "\x04") out = out + "\\u0004";
			else if (ch == "\x05") out = out + "\\u0005";
			else if (ch == "\x06") out = out + "\\u0006";
			else if (ch == "\x07") out = out + "\\u0007";
			else if (ch == "\x0b") out = out + "\\u000b";
			else if (ch == "\x0c") out = out + "\\u000c";
			else if (ch == "\x0e") out = out + "\\u000e";
			else if (ch == "\x0f") out = out + "\\u000f";
			else if (ch == "\x10") out = out + "\\u0010";
			else if (ch == "\x11") out = out + "\\u0011";
			else if (ch == "\x12") out = out + "\\u0012";
			else if (ch == "\x13") out = out + "\\u0013";
			else if (ch == "\x14") out = out + "\\u0014";
			else if (ch == "\x15") out = out + "\\u0015";
			else if (ch == "\x16") out = out + "\\u0016";
			else if (ch == "\x17") out = out + "\\u0017";
			else if (ch == "\x18") out = out + "\\u0018";
			else if (ch == "\x19") out = out + "\\u0019";
			else if (ch == "\x1a") out = out + "\\u001a";
			else if (ch == "\x1b") out = out + "\\u001b";
			else if (ch == "\x1c") out = out + "\\u001c";
			else if (ch == "\x1d") out = out + "\\u001d";
			else if (ch == "\x1e") out = out + "\\u001e";
			else if (ch == "\x1f") out = out + "\\u001f";
			else out = out + ch;
		}
		return out + "\"";
	}

	function _Json(value)
	{
		if (value == null) return "null";
		local kind = typeof(value);
		if (kind == "string") return this._EscapeString(value);
		if (kind == "bool") return value ? "true" : "false";
		if (kind == "integer") return "" + value;
		/* Events contain integer measurements; quote an unexpected float so NaN/Inf cannot make invalid JSON. */
		if (kind == "float") return this._EscapeString("" + value);
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
				out = out + this._EscapeString("" + key) + ":" + this._Json(item);
			}
			return out + "}";
		}
		return this._EscapeString("" + value);
	}

	function _Emit(kind, fields = null)
	{
		local event = { protocol = 1, kind = kind, tick = GSController.GetTick() };
		if (fields != null) {
			foreach (key, value in fields) event[key] <- value;
		}
		/* GSLog preserves this message as one line; the harness extracts the JSON suffix. */
		GSLog.Info("COPILOT_EVENT " + this._Json(event));
	}

	function _SleepForever()
	{
		while (true) GSController.Sleep(1000);
	}

	function _CompanyState()
	{
		return {
			cash = GSCompany.GetBankBalance(this.company),
			loan = GSCompany.GetLoanAmount()
		};
	}

	function _TileRow(tile)
	{
		local station = GSStation.GetStationID(tile);
		return {
			tile = tile,
			x = GSMap.GetTileX(tile),
			y = GSMap.GetTileY(tile),
			tracks = GSRail.GetRailTracks(tile),
			rail_type = GSRail.IsRailTile(tile) ? GSRail.GetRailType(tile) : GSRail.RAILTYPE_INVALID,
			owner = GSTile.GetOwner(tile),
			station = station
		};
	}

	function _TilesRow(tiles)
	{
		local rows = [];
		foreach (tile in tiles) rows.append(this._TileRow(tile));
		return rows;
	}

	function _SameRows(left, right)
	{
		if (left.len() != right.len()) return false;
		for (local i = 0; i < left.len(); i++) {
			if (this._Json(left[i]) != this._Json(right[i])) return false;
		}
		return true;
	}

	function _FindHuman()
	{
		local clients = GSClientList();
		for (local id = clients.Begin(); !clients.IsEnd(); id = clients.Next()) {
			local name = GSClient.GetName(id);
			if (name == COPILOT_CLIENT_NAME) {
				local company = GSCompany.ResolveCompanyID(GSClient.GetCompany(id));
				if (company != GSCompany.COMPANY_INVALID) {
					return { client = id, name = name, company = company };
				}
			}
		}
		return null;
	}

	function _WaitForHuman()
	{
		for (local wait = 0; wait < COPILOT_MAX_CLIENT_WAITS; wait++) {
			local found = this._FindHuman();
			if (found != null) return found;
			GSController.Sleep(1);
		}
		throw "named connected human client not found: " + COPILOT_CLIENT_NAME;
	}

	function _CargoLabels(list)
	{
		local labels = [];
		for (local item = list.Begin(); !list.IsEnd(); item = list.Next()) {
			local label = GSCargo.GetCargoLabel(item);
			if (label != null) labels.append(label);
		}
		return labels;
	}

	function _DiscoverCargoAndIndustries()
	{
		local cargo_list = GSCargoList();
		for (local item = cargo_list.Begin(); !cargo_list.IsEnd(); item = cargo_list.Next()) {
			local label = GSCargo.GetCargoLabel(item);
			if (label == "COAL") this.coal = item;
		}
		if (this.coal < 0) throw "COAL cargo label is unavailable";

		local industries = GSIndustryList();
		for (local industry = industries.Begin(); !industries.IsEnd(); industry = industries.Next()) {
			local location = GSIndustry.GetLocation(industry);
			local produces = this._CargoLabels(GSCargoList_IndustryProducing(industry));
			local accepts = this._CargoLabels(GSCargoList_IndustryAccepting(industry));
			local coal_production = GSIndustry.GetLastMonthProduction(industry, this.coal);
			local coal_state = GSIndustry.IsCargoAccepted(industry, this.coal);
			local coal_producer = false;
			foreach (label in produces) if (label == "COAL") coal_producer = true;
			local coal_acceptor = coal_state == GSIndustry.CAS_ACCEPTED;
			if (coal_producer && this.producer < 0) this.producer = industry;
			if (coal_acceptor && this.acceptor < 0) this.acceptor = industry;
			this._Emit("industry", {
				industry = industry,
				name = GSIndustry.GetName(industry),
				x = GSMap.GetTileX(location),
				y = GSMap.GetTileY(location),
				location = location,
				produces = produces,
				accepts = accepts,
				coal_production = coal_production,
				coal_acceptance_state = coal_state,
				coal_producer = coal_producer,
				coal_acceptor = coal_acceptor
			});
		}
		if (this.producer < 0 || this.acceptor < 0) throw "COAL requires a producer and an accepting industry";
	}

	function _SettingsSnapshot()
	{
		local snapshot = {};
		foreach (name in ["difficulty.max_loan", "economy.inflation", "construction.command_pause_level"]) {
			if (GSGameSettings.IsValid(name)) snapshot[name] <- GSGameSettings.GetValue(name);
		}
		return snapshot;
	}

	function _DiscoverRailAndEngines()
	{
		local rail_types = GSRailTypeList();
		local available_rails = [];
		for (local rail = rail_types.Begin(); !rail_types.IsEnd(); rail = rail_types.Next()) {
			if (GSRail.IsRailTypeAvailable(rail)) available_rails.append(rail);
		}
		if (available_rails.len() == 0) throw "no available rail type";

		local engines = GSEngineList(GSVehicle.VT_RAIL);
		local saw_locomotive = false;
		local saw_coal_wagon = false;
		for (local engine = engines.Begin(); !engines.IsEnd(); engine = engines.Next()) {
			/* GSEngineList includes future/unavailable IDs; query properties only after this live filter. */
			if (!GSEngine.IsBuildable(engine)) continue;
			local is_wagon = GSEngine.IsWagon(engine);
			local rails = [];
			foreach (rail in available_rails) {
				if (!is_wagon && GSEngine.CanRunOnRail(engine, rail)) rails.append(rail);
			}
			local coal_type = GSEngine.GetCargoType(engine);
			local coal_refit = is_wagon && GSEngine.CanRefitCargo(engine, this.coal);
			local coal_wagon = is_wagon && (coal_type == this.coal || coal_refit);
			local locomotive = !is_wagon && rails.len() > 0;
			if (locomotive) saw_locomotive = true;
			if (coal_wagon) saw_coal_wagon = true;
			local row = {
				engine = engine,
				name = GSEngine.GetName(engine),
				buildable = true,
				wagon = is_wagon,
				coal_pull = !is_wagon && GSEngine.CanPullCargo(engine, this.coal),
				coal_refit = coal_refit,
				coal_wagon = coal_wagon,
				locomotive = locomotive,
				capacity = GSEngine.GetCapacity(engine),
				price = GSEngine.GetPrice(engine),
				running_cost = GSEngine.GetRunningCost(engine),
				power = is_wagon ? 0 : GSEngine.GetPower(engine),
				weight = GSEngine.GetWeight(engine),
				rail_types = rails
			};
			this._Emit("engine", row);
			if (this.chosen_rail == GSRail.RAILTYPE_INVALID && locomotive) {
				this.chosen_rail = rails[0];
			}
		}
		if (this.chosen_rail == GSRail.RAILTYPE_INVALID) throw "no buildable train and available rail type pair";
		if (!saw_locomotive || !saw_coal_wagon) throw "live engine discovery found no buildable locomotive and COAL wagon";
		GSRail.SetCurrentRailType(this.chosen_rail);
	}

	function _FlatBuildable(tile)
	{
		return GSMap.IsValidTile(tile) && GSTile.IsBuildable(tile) && GSTile.GetSlope(tile) == GSTile.SLOPE_FLAT && !GSTile.IsWaterTile(tile);
	}

	function _MakeCandidate(x, y, vertical)
	{
		local rail_tile;
		local station;
		local direction;
		local station_tiles = [];
		if (!vertical) {
			rail_tile = GSMap.GetTileIndex(x, y);
			station = GSMap.GetTileIndex(x + 1, y);
			direction = GSRail.RAILTRACK_NE_SW;
			station_tiles = [station, GSMap.GetTileIndex(x + 2, y)];
		} else {
			rail_tile = GSMap.GetTileIndex(x, y);
			station = GSMap.GetTileIndex(x, y + 1);
			direction = GSRail.RAILTRACK_NW_SE;
			station_tiles = [station, GSMap.GetTileIndex(x, y + 2)];
		}
		local rail_tiles = [rail_tile];
		if (!this._FlatBuildable(rail_tile)) return null;
		foreach (tile in station_tiles) if (!this._FlatBuildable(tile)) return null;
		return {
			x = x,
			y = y,
			vertical = vertical,
			rail_tile = rail_tile,
			rail_tiles = rail_tiles,
			station = station,
			station_tiles = station_tiles,
			direction = direction,
			track = direction,
			rail_type = this.chosen_rail
		};
	}

	function _DryRunRail(c)
	{
		local before = this._TilesRow(c.rail_tiles);
		local state_before = this._CompanyState();
		local ok;
		local estimated;
		{
			local test = GSTestMode();
			local accounting = GSAccounting();
			ok = GSRail.BuildRailTrack(c.rail_tile, c.track);
			estimated = accounting.GetCosts();
		}
		local after = this._TilesRow(c.rail_tiles);
		local state_after = this._CompanyState();
		local row = {
			piece = "rail",
			ok = ok,
			estimated_cost = estimated,
			cash_before = state_before.cash,
			cash_after = state_after.cash,
			loan_before = state_before.loan,
			loan_after = state_after.loan,
			footprint_unchanged = this._SameRows(before, after)
		};
		this._Emit("dry_run", row);
		return row;
	}

	function _DryRunStation(c)
	{
		local before = this._TilesRow(c.station_tiles);
		local state_before = this._CompanyState();
		local ok;
		local estimated;
		{
			local test = GSTestMode();
			local accounting = GSAccounting();
			ok = GSRail.BuildRailStation(c.station, c.direction, 1, 2, GSStation.STATION_NEW);
			estimated = accounting.GetCosts();
		}
		local after = this._TilesRow(c.station_tiles);
		local state_after = this._CompanyState();
		local row = {
			piece = "station",
			ok = ok,
			estimated_cost = estimated,
			cash_before = state_before.cash,
			cash_after = state_after.cash,
			loan_before = state_before.loan,
			loan_after = state_after.loan,
			footprint_unchanged = this._SameRows(before, after)
		};
		this._Emit("dry_run", row);
		return row;
	}

	function _FindCandidate()
	{
		local width = GSMap.GetMapSizeX();
		local height = GSMap.GetMapSizeY();
		local cx = width / 2;
		local cy = height / 2;
		local tried = 0;
		for (local radius = 0; radius <= 24 && tried < COPILOT_MAX_CANDIDATES; radius++) {
			for (local dy = -radius; dy <= radius && tried < COPILOT_MAX_CANDIDATES; dy++) {
				for (local dx = -radius; dx <= radius && tried < COPILOT_MAX_CANDIDATES; dx++) {
					if (radius != 0 && ((dx < 0 ? -dx : dx) != radius && (dy < 0 ? -dy : dy) != radius)) continue;
					local x = cx + dx;
					local y = cy + dy;
					for (local orientation = 0; orientation < 2 && tried < COPILOT_MAX_CANDIDATES; orientation++) {
						local vertical = orientation == 1;
						tried++;
						local c = this._MakeCandidate(x, y, vertical);
						if (c == null) continue;
						local rail = this._DryRunRail(c);
						if (!rail.ok || !rail.footprint_unchanged || rail.cash_before != rail.cash_after || rail.loan_before != rail.loan_after) continue;
						local station = this._DryRunStation(c);
						if (!station.ok || !station.footprint_unchanged || station.cash_before != station.cash_after || station.loan_before != station.loan_after) continue;
						local total = rail.estimated_cost + station.estimated_cost;
						local state = this._CompanyState();
						if (total > COPILOT_SPEND_CAP || state.cash - total < COPILOT_CASH_RESERVE) continue;
						c.rail_estimate <- rail.estimated_cost;
						c.station_estimate <- station.estimated_cost;
						c.total_estimate <- total;
						return c;
					}
				}
			}
		}
		throw "no bounded flat candidate passed test-mode accounting and budget checks";
	}

	function _BuildAndRead(c)
	{
		local before = this._CompanyState();
		if (before.cash - c.total_estimate < COPILOT_CASH_RESERVE) throw "cash reserve failed immediately before rail construction";
		local rail_ok;
		local rail_cost;
		{
			local accounting = GSAccounting();
			rail_ok = GSRail.BuildRailTrack(c.rail_tile, c.track);
			rail_cost = accounting.GetCosts();
		}
		local after = this._CompanyState();
		local rail_rows = this._TilesRow(c.rail_tiles);
		if (!rail_ok) throw "rail command rejected before readback";
		if (rail_cost != c.rail_estimate || rail_cost != before.cash - after.cash || before.loan != after.loan) throw "rail test estimate, accounting, and cash delta disagree";
		foreach (row in rail_rows) {
			if (row.tracks != c.track || row.owner != this.company || row.rail_type != this.chosen_rail) throw "rail readback ownership, type, or track mismatch";
		}
		this.progress = { company = this.company, client = this.client, candidate = c, rail_cost = rail_cost, rail_tiles = rail_rows, station_tiles = this._TilesRow(c.station_tiles), cash = after.cash, loan = after.loan, state = "rail_built_partial" };
		this._Emit("rail_built", {
			tiles = rail_rows,
			owner = this.company,
			rail_type = this.chosen_rail,
			accounting_cost = rail_cost,
			cash_before = before.cash,
			cash_after = after.cash,
			loan_before = before.loan,
			loan_after = after.loan,
			cash_delta = before.cash - after.cash
		});

		before = this._CompanyState();
		if (before.cash - c.station_estimate < COPILOT_CASH_RESERVE) throw "cash reserve failed immediately before station construction; partial rail retained";
		local station_ok;
		local station_cost;
		{
			local accounting = GSAccounting();
			station_ok = GSRail.BuildRailStation(c.station, c.direction, 1, 2, GSStation.STATION_NEW);
			station_cost = accounting.GetCosts();
		}
		after = this._CompanyState();
		local station_rows = this._TilesRow(c.station_tiles);
		this.progress = { company = this.company, client = this.client, candidate = c, rail_cost = rail_cost, station_cost = station_cost, rail_tiles = rail_rows, station_tiles = station_rows, cash = after.cash, loan = after.loan, state = "station_command_partial" };
		if (!station_ok) throw "station command rejected after rail construction; partial work retained";
		if (station_cost != c.station_estimate || station_cost != before.cash - after.cash || before.loan != after.loan) throw "station test estimate, accounting, and cash delta disagree; partial work retained";
		local station_id = GSStation.GetStationID(c.station);
		if (!GSStation.IsValidStation(station_id) || GSBaseStation.GetOwner(station_id) != this.company) throw "station readback ownership/id mismatch";
		foreach (row in station_rows) {
			if (row.station != station_id || row.owner != this.company || row.rail_type != this.chosen_rail || row.tracks != c.track) throw "station tile readback mismatch";
		}
		this._Emit("station_built", {
			station = station_id,
			tiles = station_rows,
			owner = this.company,
			rail_type = this.chosen_rail,
			accounting_cost = station_cost,
			cash_before = before.cash,
			cash_after = after.cash,
			loan_before = before.loan,
			loan_after = after.loan,
			cash_delta = before.cash - after.cash
		});
		this.progress = { company = this.company, client = this.client, candidate = c, rail_cost = rail_cost, station_cost = station_cost, station = station_id, rail_tiles = rail_rows, station_tiles = station_rows, cash = after.cash, loan = after.loan, state = "built" };
		return { rail_cost = rail_cost, station_cost = station_cost, station = station_id, rail_tiles = rail_rows, station_tiles = station_rows };
	}

	function _CheckRejection(c, built)
	{
		local before = this._CompanyState();
		local before_rail = this._TilesRow(c.rail_tiles);
		local before_station = this._TilesRow(c.station_tiles);
		local ok;
		local cost;
		local error_code;
		local error_text;
		{
			local accounting = GSAccounting();
			ok = GSRail.BuildRailTrack(c.rail_tile, c.track);
			/* Capture the engine rejection before any later API call can overwrite it. */
			error_code = GSError.GetLastError();
			error_text = GSError.GetLastErrorString();
			cost = accounting.GetCosts();
		}
		local after = this._CompanyState();
		local after_rail = this._TilesRow(c.rail_tiles);
		local after_station = this._TilesRow(c.station_tiles);
		local unchanged = this._SameRows(before_rail, after_rail) && this._SameRows(before_station, after_station);
		local passed = !ok && error_code == GSError.ERR_ALREADY_BUILT && cost == 0 && before.cash == after.cash && before.loan == after.loan && unchanged;
		this._Emit("rejection_checked", {
			command = "repeat_rail_same_track",
			accepted = ok,
			accounting_cost = cost,
			error_code = error_code,
			error_text = error_text,
			cash_before = before.cash,
			cash_after = after.cash,
			loan_before = before.loan,
			loan_after = after.loan,
			assets_unchanged = unchanged,
			passed = passed,
			station = built.station
		});
		if (!passed) throw "deliberate repeated rail command did not reject without mutation";
		return passed;
	}

	function _LoadedReadback()
	{
		local saved_result = this.saved != null && "result" in this.saved ? this.saved.result : null;
		local saved_progress = this.saved != null && "progress" in this.saved ? this.saved.progress : null;
		local saved_candidate = this.saved != null && "candidate" in this.saved ? this.saved.candidate : null;
		if (saved_candidate == null && saved_result != null && "candidate" in saved_result) saved_candidate = saved_result.candidate;
		local saved_state = this.saved != null && "state" in this.saved ? this.saved.state : "unknown";
		local saved_company = this.saved != null && "company" in this.saved ? this.saved.company : GSCompany.COMPANY_INVALID;
		if (saved_company == GSCompany.COMPANY_INVALID && saved_result != null && "company" in saved_result) saved_company = saved_result.company;
		local fields = {
			saved = saved_result,
			saved_state = saved_state,
			saved_progress = saved_progress,
			loaded_version = 1,
			current_company = GSCompany.COMPANY_INVALID
		};
		if (this.saved != null && "client" in this.saved) this.client = this.saved.client;
		if (saved_company != GSCompany.COMPANY_INVALID) {
			this.company = GSCompany.ResolveCompanyID(saved_company);
			fields.current_company = this.company;
			if (this.company != GSCompany.COMPANY_INVALID) {
				local mode = GSCompanyMode(this.company);
				fields.current_cash <- GSCompany.GetBankBalance(this.company);
				fields.current_loan <- GSCompany.GetLoanAmount();
			}
		}
		if (saved_candidate != null) {
			fields.saved_candidate <- saved_candidate;
			/* Candidate state stores tile IDs; partial progress rows are observational output. */
			if ("rail_tiles" in saved_candidate) fields.current_rail_tiles <- this._TilesRow(saved_candidate.rail_tiles);
			if ("station_tiles" in saved_candidate) fields.current_station_tiles <- this._TilesRow(saved_candidate.station_tiles);
		}
		this._Emit("loaded_readback", fields);
		this.state = "loaded_readback";
	}

	function _Fail(detail)
	{
		this.state = "failed";
		local fields = { detail = "" + detail, company = this.company, client = this.client, state = this.state };
		if (this.progress != null) fields.progress <- this.progress;
		if (this.candidate != null) {
			fields.candidate <- this.candidate;
			local company = GSCompany.ResolveCompanyID(this.company);
			if (company != GSCompany.COMPANY_INVALID) {
				local mode = GSCompanyMode(company);
				fields.rail_tiles <- this._TilesRow(this.candidate.rail_tiles);
				fields.station_tiles <- this._TilesRow(this.candidate.station_tiles);
				fields.cash <- GSCompany.GetBankBalance(company);
				fields.loan <- GSCompany.GetLoanAmount();
			}
		}
		this.result = fields;
		this._Emit("probe_failed", fields);
	}

	function Start()
	{
		if (this.loaded) {
			this._LoadedReadback();
			this._SleepForever();
			return;
		}
		this.started = true;
		this.state = "started";
		this._Emit("probe_started", { client_name = COPILOT_CLIENT_NAME, spend_cap = COPILOT_SPEND_CAP, cash_reserve = COPILOT_CASH_RESERVE });
		try {
			local human = this._WaitForHuman();
			this.client = human.client;
			this.company = human.company;
			local mode = GSCompanyMode(this.company);
			this.state = "human_company";
			local company_state = this._CompanyState();
			this._Emit("human_company", {
				client = this.client,
				client_name = human.name,
				company = this.company,
				company_name = GSCompany.GetName(this.company),
				cash = company_state.cash,
				loan = company_state.loan,
				map_width = GSMap.GetMapSizeX(),
				map_height = GSMap.GetMapSizeY(),
				landscape = GSGame.GetLandscape(),
				date = GSDate.GetCurrentDate(),
				settings = this._SettingsSnapshot(),
				resolved = GSCompany.ResolveCompanyID(this.company) != GSCompany.COMPANY_INVALID
			});
			this._DiscoverCargoAndIndustries();
			this._DiscoverRailAndEngines();
			this.candidate = this._FindCandidate();
			this._Emit("candidate", this.candidate);
			local built = this._BuildAndRead(this.candidate);
			local total_cost = built.rail_cost + built.station_cost;
			if (total_cost > COPILOT_SPEND_CAP) throw "actual construction cost exceeded spend cap";
			local final_state = this._CompanyState();
			if (final_state.cash < COPILOT_CASH_RESERVE || final_state.loan != company_state.loan) throw "cash reserve or loan invariant failed";
			this._CheckRejection(this.candidate, built);
			this.result = {
				company = this.company,
				client = this.client,
				producer = this.producer,
				acceptor = this.acceptor,
				coal = this.coal,
				rail_type = this.chosen_rail,
				rail_track = this.candidate.track,
				rail_cost = built.rail_cost,
				station_cost = built.station_cost,
				total_cost = total_cost,
				cash_before = company_state.cash,
				cash_after = final_state.cash,
				loan_before = company_state.loan,
				loan_after = final_state.loan,
				candidate = this.candidate,
				rail_tiles = this.candidate.rail_tiles,
				station_tiles = this.candidate.station_tiles,
				station = built.station,
				checks = {
					human_company_associated = true,
					coal_producer_and_acceptor = true,
					dry_run_unchanged = true,
					spend_cap = total_cost <= COPILOT_SPEND_CAP,
					cash_reserve = final_state.cash >= COPILOT_CASH_RESERVE,
					loan_unchanged = final_state.loan == company_state.loan,
					rail_readback = true,
					station_readback = true,
					rejection_no_mutation = true
				}
			};
			this.state = "complete";
			this._Emit("probe_complete", this.result);
		} catch (error) {
			this._Fail(error);
		}
		this._SleepForever();
	}

	function Save()
	{
		if (this.loaded && this.saved != null) return this.saved;
		return {
			protocol = 1,
			started = this.started,
			state = this.state,
			company = this.company,
			client = this.client,
			candidate = this.candidate,
			progress = this.progress,
			result = this.result
		};
	}

	function Load(version, data)
	{
		this.loaded = true;
		this.saved = data;
		this.state = "loaded";
	}
}
