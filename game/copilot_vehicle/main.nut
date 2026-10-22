/*
 * S3b disposable vehicle fixture. The harness stages the S3a controller as
 * lifecycle.nut so protocol, binding, world identity, journal, and replies
 * remain identical to the already tested lifecycle probe.
 */
require("lifecycle.nut");

COPILOT_VEHICLE_FIXTURE_CAP <- 20000;
COPILOT_VEHICLE_MUTATION_CAP <- 50000;
COPILOT_VEHICLE_MAX_EVENTS <- 32;
COPILOT_VEHICLE_MAX_SITES <- 4096;

class CopilotVehicle extends CopilotLifecycle {
	fixture_state = "none";
	fixture_payload = null;
	fixture = null;
	vehicle_id = GSVehicle.VEHICLE_INVALID;
	configured = false;
	started = false;
	monitor_started = false;
	full_sample = null;
	awaiting_delivery = false;
	suppress_delivery_chunks = false;
	telemetry_events = [];
	departure_count = 0;
	delivery_count = 0;
	telemetry_gap = null;

	function _ListHas(list, wanted)
	{
		for (local item = list.Begin(); !list.IsEnd(); item = list.Next()) if (item == wanted) return true;
		return false;
	}

	function _Diagnostic(value) { return value == null ? "null" : "" + value; }

	function _CoalCargo()
	{
		local cargos = GSCargoList();
		for (local cargo = cargos.Begin(); !cargos.IsEnd(); cargo = cargos.Next()) {
			if (GSCargo.GetCargoLabel(cargo) == "COAL") return cargo;
		}
		return -1;
	}

	function _IndustryTypes(coal)
	{
		local source = -1;
		local destination = -1;
		local types = GSIndustryTypeList();
		for (local type = types.Begin(); !types.IsEnd(); type = types.Next()) {
			if (!GSIndustryType.CanBuildIndustry(type)) continue;
			if (source < 0 && this._ListHas(GSIndustryType.GetProducedCargo(type), coal)) source = type;
			if (destination < 0 && this._ListHas(GSIndustryType.GetAcceptedCargo(type), coal)) destination = type;
		}
		return { source = source, destination = destination };
	}

	function _RailAndEngines(coal, company)
	{
		local mode = GSCompanyMode(company);
		local answer = null;
		local rails = GSRailTypeList();
		for (local rail = rails.Begin(); !rails.IsEnd(); rail = rails.Next()) {
			if (!GSRail.IsRailTypeAvailable(rail)) continue;
			local engine = -1;
			local wagon = -1;
			local engine_quote = 0;
			local wagon_quote = 0;
			local engines = GSEngineList(GSVehicle.VT_RAIL);
			for (local candidate = engines.Begin(); !engines.IsEnd(); candidate = engines.Next()) {
				if (!GSEngine.IsBuildable(candidate) || !GSEngine.CanRunOnRail(candidate, rail)) continue;
				local price = GSEngine.GetPrice(candidate);
				if (price < 0) continue;
				if (!GSEngine.IsWagon(candidate)) {
					if (!GSEngine.CanPullCargo(candidate, coal) || !GSEngine.HasPowerOnRail(candidate, rail)) continue;
					if (engine < 0 || price < engine_quote) { engine = candidate; engine_quote = price; }
				} else {
					local native_cargo = GSEngine.GetCargoType(candidate);
					if (native_cargo != coal && !GSEngine.CanRefitCargo(candidate, coal)) continue;
					if (wagon < 0 || price < wagon_quote) { wagon = candidate; wagon_quote = price; }
				}
			}
			if (engine < 0 || wagon < 0) continue;
			local total = engine_quote + wagon_quote;
			if (answer == null || total < answer.total) {
				answer = { rail_type = rail, engine = engine, wagon = wagon, engine_quote = engine_quote, wagon_quote = wagon_quote, total = total };
			}
		}
		return answer;
	}

	function _PrimaryFleetCount(company)
	{
		local mode = GSCompanyMode(company);
		local vehicles = GSVehicleList();
		/* This deliberately includes unassigned free wagons. */
		return vehicles.Count();
	}

	function _SiteAt(x, y)
	{
		local tiles = [];
		for (local dx = 0; dx < 20; dx++) {
			local tile = GSMap.GetTileIndex(x + dx, y);
			if (!this._FlatLegal(tile)) return null;
			tiles.append(tile);
		}
		local source_industry_tile = GSMap.GetTileIndex(x + 1, y - 4);
		local destination_industry_tile = GSMap.GetTileIndex(x + 18, y - 4);
		if (!this._FlatLegal(source_industry_tile) || !this._FlatLegal(destination_industry_tile)) return null;
		return {
			x = x, y = y, tiles = tiles,
			depot = tiles[0], depot_front = tiles[1],
			source_tile = tiles[1], destination_tile = tiles[18],
			source_industry_tile = source_industry_tile,
			destination_industry_tile = destination_industry_tile
		};
	}

	function _IndustriesTest(site, source_type, destination_type)
	{
		local source_ok = false;
		local destination_ok = false;
		local source_error = null;
		local destination_error = null;
		try {
			local test = GSTestMode();
			source_ok = GSIndustryType.BuildIndustry(source_type, site.source_industry_tile);
			if (!source_ok) source_error = GSError.GetLastErrorString();
			destination_ok = GSIndustryType.BuildIndustry(destination_type, site.destination_industry_tile);
			if (!destination_ok) destination_error = GSError.GetLastErrorString();
		} catch (error) { return { ok = false, source_ok = source_ok, destination_ok = destination_ok, source_error = source_error, destination_error = destination_error, exception = "" + error }; }
		return { ok = source_ok && destination_ok, source_ok = source_ok, destination_ok = destination_ok, source_error = source_error, destination_error = destination_error };
	}

	function _InfrastructureTest(site, company, rail_type)
	{
		local ok = true;
		local quote = 0;
		local failure = null;
		local last_error = null;
		try {
			local mode = GSCompanyMode(company);
			GSRail.SetCurrentRailType(rail_type);
			local test = GSTestMode();
			local accounting = GSAccounting();
			if (!GSRail.BuildRailDepot(site.depot, site.depot_front)) { ok = false; failure = "depot"; last_error = GSError.GetLastErrorString(); }
			if (!GSRail.BuildRailStation(site.source_tile, GSRail.RAILTRACK_NE_SW, 1, 2, GSStation.STATION_NEW)) { ok = false; if (failure == null) { failure = "source_station"; last_error = GSError.GetLastErrorString(); } }
			for (local i = 3; i <= 17; i++) if (!GSRail.BuildRailTrack(site.tiles[i], GSRail.RAILTRACK_NE_SW)) { ok = false; if (failure == null) { failure = "rail_" + i; last_error = GSError.GetLastErrorString(); } }
			if (!GSRail.BuildRailStation(site.destination_tile, GSRail.RAILTRACK_NE_SW, 1, 2, GSStation.STATION_NEW)) { ok = false; if (failure == null) { failure = "destination_station"; last_error = GSError.GetLastErrorString(); } }
			quote = accounting.GetCosts();
		} catch (error) { return { ok = false, quote = quote, failure = "exception", last_error = "" + error }; }
		return { ok = ok, quote = quote, failure = failure, last_error = last_error };
	}

	function _FindSite(source_type, destination_type, company, rail_type)
	{
		local width = GSMap.GetMapSizeX();
		local height = GSMap.GetMapSizeY();
		local max_x = width - 20;
		if (max_x > 100) max_x = 100;
		local max_y = height - 1;
		if (max_y > 100) max_y = 100;
		local tried = 0;
		local flat_sites = 0;
		local source_industry_failures = 0;
		local destination_industry_failures = 0;
		local infrastructure_failures = 0;
		local last_industry_error = null;
		local last_infrastructure_error = null;
		for (local y = 24; y <= max_y && tried < COPILOT_VEHICLE_MAX_SITES; y++) {
			for (local x = 20; x <= max_x && tried < COPILOT_VEHICLE_MAX_SITES; x++) {
				tried++;
				local site = this._SiteAt(x, y);
				if (site == null) continue;
				flat_sites++;
				local industry_test = this._IndustriesTest(site, source_type, destination_type);
				if (!industry_test.ok) {
					if (!industry_test.source_ok) { source_industry_failures++; last_industry_error = industry_test.source_error; }
					if (!industry_test.destination_ok) { destination_industry_failures++; last_industry_error = industry_test.destination_error; }
					if ("exception" in industry_test) last_industry_error = industry_test.exception;
					continue;
				}
				local test = this._InfrastructureTest(site, company, rail_type);
				if (!test.ok || test.quote < 0) { infrastructure_failures++; last_infrastructure_error = this._Diagnostic(test.failure) + ":" + this._Diagnostic(test.last_error); continue; }
				site.quote <- test.quote;
				GSLog.Info("COPILOT_VEHICLE site_search tried=" + tried + " flat=" + flat_sites + " source_fail=" + source_industry_failures + " destination_fail=" + destination_industry_failures + " infrastructure_fail=" + infrastructure_failures);
				return site;
			}
		}
		GSLog.Warning("COPILOT_VEHICLE site_search_failed tried=" + tried + " flat=" + flat_sites + " source_fail=" + source_industry_failures + " destination_fail=" + destination_industry_failures + " infrastructure_fail=" + infrastructure_failures + " industry_error=" + this._Diagnostic(last_industry_error) + " infrastructure_error=" + this._Diagnostic(last_infrastructure_error));
		return null;
	}

	function _IndustrySet()
	{
		local set = {};
		local industries = GSIndustryList();
		for (local id = industries.Begin(); !industries.IsEnd(); id = industries.Next()) set[id] <- true;
		return set;
	}

	function _NewIndustry(before)
	{
		local industries = GSIndustryList();
		for (local id = industries.Begin(); !industries.IsEnd(); id = industries.Next()) if (!(id in before)) return id;
		return -1;
	}

	function _StationAccepts(station, cargo)
	{
		return this._ListHas(GSCargoList_StationAccepting(station), cargo);
	}

	function _FixtureReply(request, duplicate = false)
	{
		local fields = { fixture = this.fixture, state = this.fixture_state };
		if (duplicate) fields.duplicate <- true;
		return this._Reply(request, true, fields);
	}

	function _Fixture(request)
	{
		local error = this._RequireBound(request);
		if (error != null) return this._Error(request, error);
		foreach (key in ["company", "cap"]) if (!(key in request)) return this._Error(request, "field_required");
		if (!this._IsInteger(request.company) || !this._IsInteger(request.cap)) return this._Error(request, "invalid_field_type");
		local payload = { company = request.company, cap = request.cap };
		if (this.fixture_state != "none") {
			if (this.fixture_payload == null || this._Json(this.fixture_payload) != this._Json(payload)) return this._Error(request, "id_conflict");
			if (this.fixture_state == "completed") return this._FixtureReply(request, true);
			return this._Error(request, "uncertain_pending");
		}
		if (request.company != this.bound_company) return this._Error(request, "company_mismatch");
		if (request.cap < 0 || request.cap > COPILOT_VEHICLE_FIXTURE_CAP) return this._Error(request, "invalid_cap");
		if (GSGame.IsPaused()) return this._Error(request, "paused");
		if (this._PrimaryFleetCount(this.bound_company) != 0) return this._Error(request, "fixture_requires_empty_fleet");

		local coal = this._CoalCargo();
		if (coal < 0) return this._Error(request, "coal_unavailable");
		local types = this._IndustryTypes(coal);
		if (types.source < 0 || types.destination < 0) return this._Error(request, "coal_industries_unavailable");
		local selection = this._RailAndEngines(coal, this.bound_company);
		if (selection == null) return this._Error(request, "coal_train_unavailable");
		GSLog.Info("COPILOT_VEHICLE selection rail=" + selection.rail_type + " engine=" + selection.engine + " wagon=" + selection.wagon + " engine_quote=" + selection.engine_quote + " wagon_quote=" + selection.wagon_quote);
		local site = this._FindSite(types.source, types.destination, this.bound_company, selection.rail_type);
		if (site == null) return this._Error(request, "no_feasible_fixture");
		if (site.quote > request.cap) return this._Error(request, "cap");
		local before = this._CompanyState(this.bound_company);
		if (before.cash - site.quote < COPILOT_LIFECYCLE_RESERVE) return this._Error(request, "reserve");

		this.fixture_payload = payload;
		this.fixture_state = "pending";
		local source_industry = -1;
		local destination_industry = -1;
		local cost = 0;
		try {
			local industries_before = this._IndustrySet();
			if (!GSIndustryType.BuildIndustry(types.source, site.source_industry_tile)) throw "source_industry";
			source_industry = this._NewIndustry(industries_before);
			if (source_industry < 0) throw "source_industry_id";
			/* Make the disposable source deterministic and fast enough for two
			 * observed cycles. This is deity-only fixture setup, never a player
			 * company mutation or a production policy for the Copilot. */
			{
				/* COMPANY_INVALID selects deity mode for GameScript commands. */
				local deity = GSCompanyMode(GSCompany.COMPANY_INVALID);
				/* Some 15.3 industry types reject external production control;
				 * retain their normal production in that case and verify actual
				 * cargo at the station below. */
				GSIndustry.SetProductionLevel(source_industry, 128, false, null);
			}
			industries_before = this._IndustrySet();
			if (!GSIndustryType.BuildIndustry(types.destination, site.destination_industry_tile)) throw "destination_industry";
			destination_industry = this._NewIndustry(industries_before);
			if (destination_industry < 0) throw "destination_industry_id";

			local after_industries_test = this._InfrastructureTest(site, this.bound_company, selection.rail_type);
			if (after_industries_test == null || !after_industries_test.ok || after_industries_test.quote > request.cap) throw "infrastructure_retest";
			before = this._CompanyState(this.bound_company);
			if (before.cash - after_industries_test.quote < COPILOT_LIFECYCLE_RESERVE) throw "reserve_retest";
			{
				local mode = GSCompanyMode(this.bound_company);
				GSRail.SetCurrentRailType(selection.rail_type);
				local accounting = GSAccounting();
				if (!GSRail.BuildRailDepot(site.depot, site.depot_front)) throw "depot";
				if (!GSRail.BuildRailStation(site.source_tile, GSRail.RAILTRACK_NE_SW, 1, 2, GSStation.STATION_NEW)) throw "source_station";
				for (local i = 3; i <= 17; i++) if (!GSRail.BuildRailTrack(site.tiles[i], GSRail.RAILTRACK_NE_SW)) throw "rail";
				if (!GSRail.BuildRailStation(site.destination_tile, GSRail.RAILTRACK_NE_SW, 1, 2, GSStation.STATION_NEW)) throw "destination_station";
				cost = accounting.GetCosts();
			}
			local after = this._CompanyState(this.bound_company);
			local source_station = GSStation.GetStationID(site.source_tile);
			local destination_station = GSStation.GetStationID(site.destination_tile);
			if (!GSStation.IsValidStation(source_station) || !GSStation.IsValidStation(destination_station)) throw "station_readback";
			local coverage = GSStation.GetCoverageRadius(GSStation.STATION_TRAIN);
			if (GSTile.GetCargoProduction(site.source_tile, coal, 2, 1, coverage) <= 0) throw "source_not_covering_coal";
			if (!this._StationAccepts(destination_station, coal)) throw "destination_not_accepting_coal";
			if (!this._ListHas(GSCargoList_IndustryProducing(source_industry), coal)) throw "source_not_producing_coal";
			if (GSIndustry.IsCargoAccepted(destination_industry, coal) != GSIndustry.CAS_ACCEPTED) throw "destination_industry_not_accepting_coal";
			if (cost < 0 || cost > request.cap || before.cash - after.cash != cost || before.loan != after.loan) throw "accounting";
			if (!GSRail.IsRailDepotTile(site.depot) || GSRail.GetRailDepotFrontTile(site.depot) != site.depot_front) throw "depot_readback";
			this.fixture = {
				company = this.bound_company, cargo = coal, engine = selection.engine, wagon = selection.wagon,
				depot = site.depot, source_tile = site.source_tile, destination_tile = site.destination_tile,
				source_station = source_station, destination_station = destination_station,
				source_industry = source_industry, destination_industry = destination_industry,
				rail_type = selection.rail_type, cost = cost,
				engine_quote = selection.engine_quote, wagon_quote = selection.wagon_quote
			};
			this.fixture_state = "completed";
			return this._FixtureReply(request);
		} catch (fixture_error) {
			this.fixture_state = "uncertain";
			this._LogError("fixture_uncertain detail=" + fixture_error);
			return this._Error(request, "uncertain");
		}
	}

	function _MutationPayload(request, kind)
	{
		local payload = { kind = kind, company = request.company, cap = request.cap, expect_seq = request.expect_seq };
		if (kind == "purchase") payload.engine <- ("engine" in request) ? request.engine : this.fixture.engine;
		return payload;
	}

	function _MutationCheck(request, kind)
	{
		local error = this._RequireBound(request);
		if (error != null) return error;
		foreach (key in ["op", "company", "cap", "expect_seq"]) if (!(key in request)) return "field_required";
		if (!this._IsString(request.op)) return "invalid_op";
		foreach (key in ["company", "cap", "expect_seq"]) if (!this._IsInteger(request[key])) return "invalid_field_type";
		if (kind == "purchase" && "engine" in request && !this._IsInteger(request.engine)) return "invalid_field_type";
		if (request.company != this.bound_company) return "company_mismatch";
		if (request.cap < 0 || request.cap > COPILOT_VEHICLE_MUTATION_CAP) return "invalid_cap";
		if (request.expect_seq < 0) return "seq_mismatch";
		if (GSGame.IsPaused()) return "paused";
		if (this.fixture_state != "completed" || this.fixture == null) return "fixture_required";
		return null;
	}

	function _ExistingMutation(request, payload)
	{
		local entry = this._JournalEntry(request.op);
		if (entry == null) return null;
		if (this._Json(entry.payload) != this._Json(payload)) return { conflict = true };
		return { conflict = false, outcome = entry.outcome };
	}

	function _MutationReply(request, outcome, duplicate = false)
	{
		local fields = { state = outcome.state, outcome = outcome };
		if (duplicate) fields.duplicate <- true;
		return this._Reply(request, true, fields);
	}

	function _RejectedMutation(request, payload, reason)
	{
		local state = this._CompanyState(this.bound_company);
		local outcome = { state = "rejected", op = request.op, reason = reason, vehicle = this.vehicle_id, cost = 0, cash = state.cash, loan = state.loan, seq = this.seq };
		this.journal.append({ op = request.op, payload = payload, outcome = outcome });
		return this._MutationReply(request, outcome);
	}

	function _UncertainMutation(request, payload, cost, detail)
	{
		local state = this._CompanyState(this.bound_company);
		local outcome = { state = "uncertain", op = request.op, vehicle = this.vehicle_id, cost = cost, cash = state.cash, loan = state.loan, seq = this.seq, detail = detail };
		this.pending.outcome <- outcome;
		return this._Reply(request, false, { error = "uncertain", state = "uncertain", outcome = outcome });
	}

	function _CompleteMutation(request, payload, cost)
	{
		this.seq++;
		this.head = request.op;
		local state = this._CompanyState(this.bound_company);
		local outcome = { state = "completed", op = request.op, vehicle = this.vehicle_id, cost = cost, cash = state.cash, loan = state.loan, seq = this.seq };
		this.journal.append({ op = request.op, payload = payload, outcome = outcome });
		this.pending = null;
		return this._MutationReply(request, outcome);
	}

	function _BeginMutation(request, payload)
	{
		this.pending = {
			op = request.op, payload = payload, started_tick = GSController.GetTick(),
			outcome = { state = "uncertain", op = request.op, vehicle = this.vehicle_id, cost = null, cash = null, loan = null, seq = this.seq }
		};
	}

	function _Purchase(request)
	{
		local error = this._MutationCheck(request, "purchase");
		if (error != null) return this._Error(request, error);
		local payload = this._MutationPayload(request, "purchase");
		local existing = this._ExistingMutation(request, payload);
		if (existing != null) return existing.conflict ? this._Error(request, "id_conflict") : this._MutationReply(request, existing.outcome, true);
		if (this.pending != null) return this._Error(request, "uncertain_pending");
		if (this.journal.len() >= COPILOT_LIFECYCLE_MAX_JOURNAL) return this._Error(request, "journal_full");
		if (existing == null && request.expect_seq != this.seq) return this._Error(request, "seq_mismatch");
		local requested_engine = ("engine" in request) ? request.engine : this.fixture.engine;
		if (requested_engine != this.fixture.engine) return this._Error(request, "engine_mismatch");
		if (this.vehicle_id != GSVehicle.VEHICLE_INVALID || this._PrimaryFleetCount(this.bound_company) != 0) return this._Error(request, "vehicle_already_present");

		local before = this._CompanyState(this.bound_company);
		local estimate = 0;
		local test_vehicle = GSVehicle.VEHICLE_INVALID;
		try {
			local mode = GSCompanyMode(this.bound_company);
			local test = GSTestMode();
			local accounting = GSAccounting();
			test_vehicle = GSVehicle.BuildVehicle(this.fixture.depot, this.fixture.engine);
			estimate = accounting.GetCosts();
		} catch (test_error) { return this._Error(request, "command_test_exception"); }
		if (test_vehicle == GSVehicle.VEHICLE_INVALID) return this._RejectedMutation(request, payload, "command");
		if (estimate < 0 || estimate > request.cap) return this._RejectedMutation(request, payload, "cap");
		if (before.cash - estimate < COPILOT_LIFECYCLE_RESERVE) return this._RejectedMutation(request, payload, "reserve");

		this._BeginMutation(request, payload);
		local cost = 0;
		try {
			local after;
			{
				local mode = GSCompanyMode(this.bound_company);
				local accounting = GSAccounting();
				this.vehicle_id = GSVehicle.BuildVehicle(this.fixture.depot, this.fixture.engine);
				cost = accounting.GetCosts();
				after = this._CompanyState(this.bound_company);
				if (this.vehicle_id == GSVehicle.VEHICLE_INVALID) {
					this.pending = null;
					return this._RejectedMutation(request, payload, "command");
				}
				if (!GSVehicle.IsPrimaryVehicle(this.vehicle_id) || GSVehicle.GetEngineType(this.vehicle_id) != this.fixture.engine || !GSVehicle.IsStoppedInDepot(this.vehicle_id)) return this._UncertainMutation(request, payload, cost, "readback");
			}
			if (cost > request.cap || before.cash - after.cash != cost || before.loan != after.loan || this._PrimaryFleetCount(this.bound_company) != 1) return this._UncertainMutation(request, payload, cost, "accounting");
			return this._CompleteMutation(request, payload, cost);
		} catch (purchase_error) {
			this._LogError("purchase_exception op=" + request.op + " detail=" + purchase_error);
			return this._UncertainMutation(request, payload, cost, "exception");
		}
	}

	function _Configure(request)
	{
		local error = this._MutationCheck(request, "configure");
		if (error != null) return this._Error(request, error);
		local payload = this._MutationPayload(request, "configure");
		local existing = this._ExistingMutation(request, payload);
		if (existing != null) return existing.conflict ? this._Error(request, "id_conflict") : this._MutationReply(request, existing.outcome, true);
		if (request.expect_seq != this.seq) return this._Error(request, "seq_mismatch");
		if (this.pending != null) return this._Error(request, "uncertain_pending");
		if (this.journal.len() >= COPILOT_LIFECYCLE_MAX_JOURNAL) return this._Error(request, "journal_full");
		if (this.vehicle_id == GSVehicle.VEHICLE_INVALID || this.configured) return this._Error(request, "vehicle_not_configurable");

		local before = this._CompanyState(this.bound_company);
		local estimate = 0;
		local test_wagon = GSVehicle.VEHICLE_INVALID;
		try {
			local mode = GSCompanyMode(this.bound_company);
			local test = GSTestMode();
			local accounting = GSAccounting();
			test_wagon = GSVehicle.BuildVehicleWithRefit(this.fixture.depot, this.fixture.wagon, this.fixture.cargo);
			estimate = accounting.GetCosts();
		} catch (test_error) { return this._Error(request, "command_test_exception"); }
		if (test_wagon == GSVehicle.VEHICLE_INVALID) return this._RejectedMutation(request, payload, "command");
		if (estimate < 0 || estimate > request.cap) return this._RejectedMutation(request, payload, "cap");
		if (before.cash - estimate < COPILOT_LIFECYCLE_RESERVE) return this._RejectedMutation(request, payload, "reserve");

		this._BeginMutation(request, payload);
		local cost = 0;
		try {
			local wagon_id = GSVehicle.VEHICLE_INVALID;
			local after;
			{
				local mode = GSCompanyMode(this.bound_company);
				local accounting = GSAccounting();
				wagon_id = GSVehicle.BuildVehicleWithRefit(this.fixture.depot, this.fixture.wagon, this.fixture.cargo);
				if (wagon_id == GSVehicle.VEHICLE_INVALID) {
					cost = accounting.GetCosts();
					this.pending = null;
					return this._RejectedMutation(request, payload, "command");
				}
				if (!GSVehicle.MoveWagonChain(wagon_id, 0, this.vehicle_id, 0)) { cost = accounting.GetCosts(); return this._UncertainMutation(request, payload, cost, "attach"); }
				if (!GSOrder.AppendOrder(this.vehicle_id, this.fixture.source_tile, GSOrder.OF_FULL_LOAD)) { cost = accounting.GetCosts(); return this._UncertainMutation(request, payload, cost, "source_order"); }
				if (!GSOrder.AppendOrder(this.vehicle_id, this.fixture.destination_tile, GSOrder.OF_UNLOAD | GSOrder.OF_NO_LOAD)) { cost = accounting.GetCosts(); return this._UncertainMutation(request, payload, cost, "destination_order"); }
				cost = accounting.GetCosts();
				after = this._CompanyState(this.bound_company);
				if (GSVehicle.GetNumWagons(this.vehicle_id) != 2 || GSVehicle.GetWagonEngineType(this.vehicle_id, 1) != this.fixture.wagon || GSVehicle.GetCapacity(this.vehicle_id, this.fixture.cargo) <= 0) return this._UncertainMutation(request, payload, cost, "consist_readback");
				if (GSOrder.GetOrderCount(this.vehicle_id) != 2 || GSOrder.GetOrderDestination(this.vehicle_id, 0) != this.fixture.source_tile || GSOrder.GetOrderFlags(this.vehicle_id, 0) != GSOrder.OF_FULL_LOAD || GSOrder.GetOrderDestination(this.vehicle_id, 1) != this.fixture.destination_tile || GSOrder.GetOrderFlags(this.vehicle_id, 1) != (GSOrder.OF_UNLOAD | GSOrder.OF_NO_LOAD)) return this._UncertainMutation(request, payload, cost, "order_readback");
			}
			if (cost > request.cap || before.cash - after.cash != cost || before.loan != after.loan || this._PrimaryFleetCount(this.bound_company) != 1) return this._UncertainMutation(request, payload, cost, "accounting");
			this.configured = true;
			GSCargoMonitor.GetIndustryDeliveryAmount(this.bound_company, this.fixture.cargo, this.fixture.destination_industry, true);
			this.monitor_started = true;
			return this._CompleteMutation(request, payload, cost);
		} catch (configure_error) {
			this._LogError("configure_exception op=" + request.op + " detail=" + configure_error);
			return this._UncertainMutation(request, payload, cost, "exception");
		}
	}

	function _Start(request)
	{
		local error = this._MutationCheck(request, "start");
		if (error != null) return this._Error(request, error);
		local payload = this._MutationPayload(request, "start");
		local existing = this._ExistingMutation(request, payload);
		if (existing != null) return existing.conflict ? this._Error(request, "id_conflict") : this._MutationReply(request, existing.outcome, true);
		if (request.expect_seq != this.seq) return this._Error(request, "seq_mismatch");
		if (this.pending != null) return this._Error(request, "uncertain_pending");
		if (this.journal.len() >= COPILOT_LIFECYCLE_MAX_JOURNAL) return this._Error(request, "journal_full");
		if (!this.configured || this.vehicle_id == GSVehicle.VEHICLE_INVALID || this.started) return this._Error(request, "vehicle_not_startable");
		local before = this._CompanyState(this.bound_company);
		this._BeginMutation(request, payload);
		try {
			local mode = GSCompanyMode(this.bound_company);
			if (!GSVehicle.StartStopVehicle(this.vehicle_id)) {
				this.pending = null;
				return this._RejectedMutation(request, payload, "command");
			}
			local after = this._CompanyState(this.bound_company);
			if (GSVehicle.IsStoppedInDepot(this.vehicle_id) || before.cash != after.cash || before.loan != after.loan) return this._UncertainMutation(request, payload, 0, "readback");
			this.started = true;
			return this._CompleteMutation(request, payload, 0);
		} catch (start_error) {
			this._LogError("start_exception op=" + request.op + " detail=" + start_error);
			return this._UncertainMutation(request, payload, 0, "exception");
		}
	}

	function _VehicleSnapshot()
	{
		if (this.fixture == null || this.vehicle_id == GSVehicle.VEHICLE_INVALID) return null;
		local mode = GSCompanyMode(this.fixture.company);
		if (!GSVehicle.IsValidVehicle(this.vehicle_id) || !GSVehicle.IsPrimaryVehicle(this.vehicle_id)) return null;
		local orders = [];
		local count = GSOrder.GetOrderCount(this.vehicle_id);
		for (local i = 0; i < count && i < 8; i++) orders.append({ destination = GSOrder.GetOrderDestination(this.vehicle_id, i), flags = GSOrder.GetOrderFlags(this.vehicle_id, i) });
		local state = this._CompanyState(this.fixture.company);
		return {
			id = this.vehicle_id, engine = GSVehicle.GetEngineType(this.vehicle_id), depot = this.fixture.depot,
			state = GSVehicle.GetState(this.vehicle_id), in_depot = GSVehicle.IsInDepot(this.vehicle_id), stopped_in_depot = GSVehicle.IsStoppedInDepot(this.vehicle_id),
			num_wagons = GSVehicle.GetNumWagons(this.vehicle_id), capacity = GSVehicle.GetCapacity(this.vehicle_id, this.fixture.cargo),
			load = GSVehicle.GetCargoLoad(this.vehicle_id, this.fixture.cargo), length = GSVehicle.GetLength(this.vehicle_id), location = GSVehicle.GetLocation(this.vehicle_id),
			current_order = GSOrder.ResolveOrderPosition(this.vehicle_id, GSOrder.ORDER_CURRENT), orders = orders,
			fleet_count = this._PrimaryFleetCount(this.fixture.company), profit = GSVehicle.GetProfitThisYear(this.vehicle_id), cash = state.cash, loan = state.loan
		};
	}

	function _Vehicle(request)
	{
		local error = this._RequireWorld(request);
		if (error != null) return this._Error(request, error);
		return this._Reply(request, true, { vehicle = this._VehicleSnapshot() });
	}

	function _PushTelemetry(event)
	{
		if (this.telemetry_events.len() >= COPILOT_VEHICLE_MAX_EVENTS) {
			this.telemetry_gap = "telemetry_overflow";
			return false;
		}
		this.telemetry_events.append(event);
		return true;
	}

	function _Observe()
	{
		if (!this.monitor_started || this.fixture == null || this.vehicle_id == GSVehicle.VEHICLE_INVALID) return;
		try {
			local mode = GSCompanyMode(this.fixture.company);
			if (!GSVehicle.IsPrimaryVehicle(this.vehicle_id)) { this.telemetry_gap = "vehicle_missing"; return; }
			local fleet = this._PrimaryFleetCount(this.fixture.company);
			local tick = GSController.GetTick();
			local tile = GSVehicle.GetLocation(this.vehicle_id);
			local load = GSVehicle.GetCargoLoad(this.vehicle_id, this.fixture.cargo);
			local capacity = GSVehicle.GetCapacity(this.vehicle_id, this.fixture.cargo);
			local profit = GSVehicle.GetProfitThisYear(this.vehicle_id);
			local station = GSStation.GetStationID(tile);
			if (this.suppress_delivery_chunks && station != this.fixture.destination_station) this.suppress_delivery_chunks = false;
			if (fleet == 1 && station == this.fixture.source_station && GSVehicle.GetState(this.vehicle_id) == GSVehicle.VS_AT_STATION && capacity > 0 && load >= capacity) {
				this.full_sample = { tick = tick, load = load, capacity = capacity, tile = tile };
			}
			if (fleet == 1 && this.full_sample != null && station != this.fixture.source_station && load >= capacity) {
				this.departure_count++;
				this._PushTelemetry({
					kind = "departure", vehicle = this.vehicle_id, tick = tick, tile = tile, source_station = this.fixture.source_station,
					load = load, capacity = capacity, fleet_count = fleet, profit = profit,
					source_tick = this.full_sample.tick, source_load = this.full_sample.load, source_capacity = this.full_sample.capacity, source_tile = this.full_sample.tile
				});
				this.full_sample = null;
				this.awaiting_delivery = true;
				this.suppress_delivery_chunks = false;
			}
			local amount = GSCargoMonitor.GetIndustryDeliveryAmount(this.fixture.company, this.fixture.cargo, this.fixture.destination_industry, true);
			if (amount > 0) {
				if (this.awaiting_delivery && fleet == 1 && station == this.fixture.destination_station) {
					this.delivery_count++;
					this._PushTelemetry({ kind = "delivery", vehicle = this.vehicle_id, tick = tick, tile = tile, destination_industry = this.fixture.destination_industry, destination_station = this.fixture.destination_station, amount = amount, load = load, capacity = capacity, fleet_count = fleet, profit = profit });
					this.awaiting_delivery = false;
					this.suppress_delivery_chunks = true;
				} else if (!this.suppress_delivery_chunks) {
					this.telemetry_gap = "unattributed_delivery";
					this._PushTelemetry({ kind = "gap", tick = tick, amount = amount, fleet_count = fleet, reason = this.telemetry_gap });
				}
			}
			if (fleet != 1) this.telemetry_gap = "fleet_not_isolated";
		} catch (observe_error) {
			this.telemetry_gap = "observe_exception";
			this._LogError("observe_exception " + observe_error);
		}
	}

	function _Telemetry(request)
	{
		local error = this._RequireWorld(request);
		if (error != null) return this._Error(request, error);
		if ("index" in request) {
			if (!this._IsInteger(request.index) || request.index < 0 || request.index >= this.telemetry_events.len()) return this._Error(request, "invalid_event");
			return this._Reply(request, true, { index = request.index, event_count = this.telemetry_events.len(), event = this.telemetry_events[request.index] });
		}
		return this._Reply(request, true, {
			scope = "isolated_one_train", attribution = "company_industry_only_when_one_primary_train",
			departures = this.departure_count, deliveries = this.delivery_count, event_count = this.telemetry_events.len(), gap = this.telemetry_gap,
			vehicle = this._VehicleSnapshot(), source_waiting = GSStation.GetCargoWaiting(this.fixture.source_station, this.fixture.cargo),
			source_production = GSIndustry.GetLastMonthProduction(this.fixture.source_industry, this.fixture.cargo),
			source_level = GSIndustry.GetProductionLevel(this.fixture.source_industry)
		});
	}

	function _Dispatch(request)
	{
		if (request == null || this._Type(request) != "table") return this._Error(null, "malformed");
		if (!("v" in request) || !this._IsInteger(request.v) || request.v != COPILOT_LIFECYCLE_VERSION) return this._Error(request, "unsupported_version");
		if (!("rid" in request) || !this._IsString(request.rid)) return this._Error(request, "invalid_rid");
		if (!("cmd" in request) || !this._IsString(request.cmd)) return this._Error(request, "invalid_command");
		{
			if (request.cmd == "fixture") return this._Fixture(request);
			if (request.cmd == "purchase") return this._Purchase(request);
			if (request.cmd == "configure") return this._Configure(request);
			if (request.cmd == "start") return this._Start(request);
			if (request.cmd == "vehicle") return this._Vehicle(request);
			if (request.cmd == "telemetry") return this._Telemetry(request);
		}
		local parent_dispatch = CopilotLifecycle._Dispatch.bindenv(this);
		return parent_dispatch(request);
	}

	function Start()
	{
		this.session = null;
		this.bound_company = GSCompany.COMPANY_INVALID;
		this.snapshot = null;
		GSLog.Info("COPILOT_VEHICLE startup loaded=" + (this.loaded ? "true" : "false") + " world=" + (this.world == null ? "null" : this.world) + " seq=" + this.seq);
		while (true) {
			this._Observe();
			if (!GSEventController.IsEventWaiting()) { GSController.Sleep(1); continue; }
			local event = GSEventController.GetNextEvent();
			try {
				if (event != null && event.GetEventType() == GSEvent.ET_ADMIN_PORT) {
					local admin = GSEventAdminPort.Convert(event);
					local request = admin.GetObject();
					try { this._Dispatch(request); }
					catch (dispatch_error) { this._LogError("dispatch_exception " + dispatch_error); this._Error(request, "internal_error"); }
				}
			} catch (event_error) { this._LogError("event_exception " + event_error); }
		}
	}

	function Save()
	{
		local parent_save = CopilotLifecycle.Save.bindenv(this);
		local data = parent_save();
		data.vehicle_protocol <- 1;
		data.fixture_state <- this.fixture_state;
		data.fixture_payload <- this.fixture_payload;
		data.fixture <- this.fixture;
		data.vehicle_id <- this.vehicle_id;
		data.configured <- this.configured;
		data.started <- this.started;
		data.monitor_started <- this.monitor_started;
		data.full_sample <- this.full_sample;
		data.awaiting_delivery <- this.awaiting_delivery;
		data.suppress_delivery_chunks <- this.suppress_delivery_chunks;
		data.telemetry_events <- this.telemetry_events;
		data.departure_count <- this.departure_count;
		data.delivery_count <- this.delivery_count;
		data.telemetry_gap <- this.telemetry_gap;
		return data;
	}

	function Load(version, data)
	{
		local parent_load = CopilotLifecycle.Load.bindenv(this);
		parent_load(version, data);
		this.fixture_state = (data != null && "fixture_state" in data) ? data.fixture_state : "none";
		this.fixture_payload = (data != null && "fixture_payload" in data) ? data.fixture_payload : null;
		this.fixture = (data != null && "fixture" in data) ? data.fixture : null;
		this.vehicle_id = (data != null && "vehicle_id" in data && this._IsInteger(data.vehicle_id)) ? data.vehicle_id : GSVehicle.VEHICLE_INVALID;
		this.configured = data != null && "configured" in data && data.configured;
		this.started = data != null && "started" in data && data.started;
		this.monitor_started = data != null && "monitor_started" in data && data.monitor_started;
		this.full_sample = (data != null && "full_sample" in data) ? data.full_sample : null;
		this.awaiting_delivery = data != null && "awaiting_delivery" in data && data.awaiting_delivery;
		this.suppress_delivery_chunks = data != null && "suppress_delivery_chunks" in data && data.suppress_delivery_chunks;
		this.telemetry_events = (data != null && "telemetry_events" in data && this._Type(data.telemetry_events) == "array") ? data.telemetry_events : [];
		this.departure_count = (data != null && "departure_count" in data && this._IsInteger(data.departure_count)) ? data.departure_count : 0;
		this.delivery_count = (data != null && "delivery_count" in data && this._IsInteger(data.delivery_count)) ? data.delivery_count : 0;
		this.telemetry_gap = (data != null && "telemetry_gap" in data) ? data.telemetry_gap : null;
	}
}
