import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { deviceName } from "../util.js";

export default function People() {
  const [people, setPeople] = useState([]);
  const [devices, setDevices] = useState([]);
  const [newName, setNewName] = useState("");

  async function refresh() {
    const [p, d] = await Promise.all([api.listPeople(), api.listDevices()]);
    setPeople(p);
    setDevices(d);
  }

  useEffect(() => {
    refresh();
  }, []);

  async function add(e) {
    e.preventDefault();
    if (!newName.trim()) return;
    await api.createPerson(newName.trim());
    setNewName("");
    refresh();
  }

  async function rename(id, name) {
    await api.renamePerson(id, name);
    refresh();
  }

  async function remove(id) {
    if (!confirm("Delete this person? Their devices become unassigned.")) return;
    await api.deletePerson(id);
    refresh();
  }

  const devicesFor = (pid) => devices.filter((d) => d.person_id === pid);

  return (
    <div className="people">
      <form className="add-person" onSubmit={add}>
        <input
          placeholder="Add a person (e.g. Brother)"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <button type="submit">Add</button>
      </form>

      <div className="cards">
        {people.map((p) => (
          <div className="card" key={p.id}>
            <div className="person-edit">
              <input
                defaultValue={p.name}
                onBlur={(e) => {
                  if (e.target.value.trim() && e.target.value !== p.name)
                    rename(p.id, e.target.value.trim());
                }}
              />
              <button className="link danger" onClick={() => remove(p.id)}>
                delete
              </button>
            </div>
            <div className="person-devices">
              {devicesFor(p.id).map((d) => (
                <span key={d.mac} className="mini">
                  {deviceName(d)}
                </span>
              ))}
              {devicesFor(p.id).length === 0 && (
                <span className="muted small">
                  no devices — assign them in the Devices tab
                </span>
              )}
            </div>
          </div>
        ))}
        {people.length === 0 && (
          <div className="muted">No people yet. Add one above.</div>
        )}
      </div>
    </div>
  );
}
