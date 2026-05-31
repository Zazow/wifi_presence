import { useEffect, useState } from "react";
import { api } from "../api";
import { avatarStyle, deviceName, initials } from "../util";
import type { Device, Person } from "../types";

export default function People() {
  const [people, setPeople] = useState<Person[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [newName, setNewName] = useState("");

  async function refresh() {
    const [p, d] = await Promise.all([api.listPeople(), api.listDevices()]);
    setPeople(p);
    setDevices(d);
  }

  useEffect(() => {
    refresh();
  }, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    await api.createPerson(newName.trim());
    setNewName("");
    refresh();
  }

  async function rename(id: number, name: string) {
    await api.renamePerson(id, name);
    refresh();
  }

  async function remove(id: number) {
    if (!confirm("Delete this person? Their devices become unassigned.")) return;
    await api.deletePerson(id);
    refresh();
  }

  const devicesFor = (pid: number) => devices.filter((d) => d.person_id === pid);

  return (
    <div className="people">
      <form className="add-person" onSubmit={add}>
        <input
          placeholder="Add a person (e.g. Brother)"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <button type="submit" className="btn btn-primary">
          Add
        </button>
      </form>

      <div className="cards">
        {people.map((p) => {
          const owned = devicesFor(p.id);
          return (
            <div className="person-card" key={p.id}>
              <div className="person-head">
                <span className="avatar" style={avatarStyle(p.name)}>
                  {initials(p.name)}
                </span>
                <input
                  className="person-name-input"
                  defaultValue={p.name}
                  onBlur={(e) => {
                    if (e.target.value.trim() && e.target.value !== p.name)
                      rename(p.id, e.target.value.trim());
                  }}
                />
                <button className="btn-link danger" onClick={() => remove(p.id)}>
                  delete
                </button>
              </div>
              <div className="person-devices">
                {owned.map((d) => (
                  <span key={d.mac} className="mini">
                    {deviceName(d)}
                  </span>
                ))}
                {owned.length === 0 && (
                  <span className="muted small">
                    no devices — assign them in the Devices tab
                  </span>
                )}
              </div>
            </div>
          );
        })}
        {people.length === 0 && <div className="muted">No people yet. Add one above.</div>}
      </div>
    </div>
  );
}
