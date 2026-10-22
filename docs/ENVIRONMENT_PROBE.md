# Existing-save and GameScript-slot probe

Status: passed in OpenTTD 15.3 against a copied representative user autosave
and the saved foreign-GameScript fixture. See the [concise evidence](evidence/2026-10-22-environment-probe.json).

The user autosave copy produced no GameScript response within the bounded
three-second window while Admin ping remained responsive. Its original hash,
size, and nanosecond modification time were identical before and after. The
foreign fixture then resumed with `loaded=true` and its saved marker while
Copilot was configured and both scripts were staged. This establishes a stock
attachment/coexistence limitation; it does not indicate a damaged save or
transport failure.

Run the bounded M1 environment experiment with an existing save that you are willing to inspect through an isolated copy:

```sh
python3 -B tools/run_environment_probe.py --save /absolute/path/to/world.sav
```

The harness never loads the supplied path directly. It fingerprints content and modification time, copies the save into a disposable server profile, stages the Copilot lifecycle GameScript, and records whether that script answers. A bounded `expected_timeout` means no GameScript answered; it is a valid compatibility result if the copied world loaded and Admin ping remained responsive. The experiment does not join a company or send a mutation request.

The second phase creates and saves a disposable world with `Foreign Environment Fixture`, then reloads a copy while both the foreign and Copilot scripts are staged and Copilot is configured. Passing evidence requires the saved foreign script to answer with its persisted marker and `loaded=true`; a Copilot-shaped control response fails the check. This tests the one-GameScript-slot limitation, not arbitrary third-party script compatibility.

Evidence and full logs remain under ignored `artifacts/environment-probe/<run>/`. The manifest records explicit timeouts, loopback listeners, engine/content/source hashes, original/copy fingerprints, zero mutation requests, normal-profile fingerprints, and secret cleanup. Do not use a normal profile as the experiment profile, and do not infer a final adapter choice from this probe alone.
