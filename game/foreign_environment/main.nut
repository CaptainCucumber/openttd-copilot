/* A deliberately distinct, read-only GameScript used to prove save-slot behavior. */

class ForeignEnvironment extends GSController {
	loaded = false;
	marker = "foreign-environment-v1";

	function Start()
	{
		GSLog.Info("FOREIGN_ENVIRONMENT startup loaded=" + (this.loaded ? "true" : "false"));
		while (true) {
			if (!GSEventController.IsEventWaiting()) { GSController.Sleep(1); continue; }
			local event = GSEventController.GetNextEvent();
			if (event == null || event.GetEventType() != GSEvent.ET_ADMIN_PORT) continue;
			try {
				local request = GSEventAdminPort.Convert(event).GetObject();
				local rid = request != null && typeof(request) == "table" && "rid" in request ? request.rid : null;
				GSAdmin.Send({ v = 1, rid = rid, ok = true, fixture = "foreign", loaded = this.loaded,
					marker = this.marker, tick = GSController.GetTick(), mutation_count = 0 });
			} catch (error) {
				GSLog.Error("FOREIGN_ENVIRONMENT admin_exception " + error);
			}
		}
	}

	function Save()
	{
		return { protocol = 1, marker = this.marker, mutation_count = 0 };
	}

	function Load(version, data)
	{
		this.loaded = true;
		if (data != null && "marker" in data) this.marker = data.marker;
	}
}
