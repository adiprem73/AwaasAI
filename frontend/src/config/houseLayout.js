// Floor-plan + device catalogue, driven entirely by data so the same canvas
// renders any household. Each household maps device_ids -> a room + render meta.
//
// Grid: a 3-column x 3-row top-view house. Rooms declare their grid placement;
// devices declare which room they live in plus an icon and toggle semantics.

export const ROOMS = {
  garden: { name: "Garden", col: "1 / 2", row: "1 / 2", accent: "#22c55e" },
  son_room: {
    name: "Son's Room",
    col: "2 / 3",
    row: "1 / 2",
    accent: "#a855f7",
  },
  bedroom: { name: "Bedroom", col: "3 / 4", row: "1 / 2", accent: "#6366f1" },
  porch: { name: "Porch", col: "1 / 2", row: "2 / 3", accent: "#eab308" },
  living_room: {
    name: "Living Room",
    col: "2 / 4",
    row: "2 / 3",
    accent: "#38bdf8",
  },
  entrance: { name: "Entrance", col: "1 / 2", row: "3 / 4", accent: "#f97316" },
  utility: { name: "Utility", col: "2 / 4", row: "3 / 4", accent: "#94a3b8" },

  // --- H003 (Indian-context home) rooms: a clean, non-overlapping 3x3 with
  // the shared son_room (2/1), porch (1/2) and entrance (1/3) cells. ---
  grandpa_room: { name: "Grandpa's Room", col: "1 / 2", row: "1 / 2", accent: "#f472b6" },
  pooja_room: { name: "Pooja Room", col: "3 / 4", row: "1 / 2", accent: "#fbbf24" },
  kitchen: { name: "Kitchen", col: "2 / 3", row: "2 / 3", accent: "#fb7185" },
  terrace: { name: "Terrace", col: "3 / 4", row: "2 / 3", accent: "#34d399" },
  store_room: { name: "Utility", col: "2 / 3", row: "3 / 4", accent: "#94a3b8" },
  grandma_room: { name: "Grandma's Room", col: "3 / 4", row: "3 / 4", accent: "#c084fc" },
};

// Per device-type rendering + on/off action semantics.
export const DEVICE_KIND = {
  fan: { icon: "🌀", onAction: "ON", offAction: "OFF", onColor: "#38bdf8" },
  light: { icon: "💡", onAction: "ON", offAction: "OFF", onColor: "#fde047" },
  ac: { icon: "❄️", onAction: "ON", offAction: "OFF", onColor: "#7dd3fc" },
  tv: { icon: "📺", onAction: "ON", offAction: "OFF", onColor: "#a78bfa" },
  motor: { icon: "🛢️", onAction: "ON", offAction: "OFF", onColor: "#fb923c" },
  door: {
    icon: "🚪",
    onAction: "OPEN",
    offAction: "CLOSE",
    onColor: "#f87171",
  },
  // --- Indian-context device kinds (H003) ---
  motor_inverter: { icon: "🔋", onAction: "ON", offAction: "OFF", onColor: "#4ade80" },
  stove: { icon: "🔥", onAction: "ON", offAction: "OFF", onColor: "#fb923c" },
  kettle: { icon: "🫖", onAction: "ON", offAction: "OFF", onColor: "#f59e0b" },
  bell: { icon: "🔔", onAction: "ON", offAction: "OFF", onColor: "#facc15" },
  speaker: { icon: "🔊", onAction: "ON", offAction: "OFF", onColor: "#a78bfa" },
  clothesline: { icon: "🧺", onAction: "ON", offAction: "OFF", onColor: "#38bdf8" },
  can: { icon: "🪣", onAction: "ON", offAction: "OFF", onColor: "#60a5fa" },
  // People / care sensors — momentary signals, shown for context.
  presence: { icon: "🧍", onAction: "ARRIVE", offAction: "LEAVE", onColor: "#34d399" },
  activity: { icon: "🚶", onAction: "ACTIVE", offAction: "IDLE", onColor: "#34d399" },
  medicine: { icon: "💊", onAction: "TAKEN", offAction: "PENDING", onColor: "#f472b6" },
};

// Households: each device has id, label, type, room.
export const HOUSEHOLDS = {
  H001: {
    label: "H001 · Son Departure Home",
    people: ["father", "mother", "son"],
    devices: [
      { id: "son_room_fan", label: "Fan", type: "fan", room: "son_room" },
      { id: "son_room_light", label: "Light", type: "light", room: "son_room" },
      { id: "living_room_ac", label: "AC", type: "ac", room: "living_room" },
      { id: "living_room_tv", label: "TV", type: "tv", room: "living_room" },
      { id: "porch_light", label: "Porch Light", type: "light", room: "porch" },
      {
        id: "water_motor",
        label: "Water Motor",
        type: "motor",
        room: "utility",
      },
    ],
  },
  H002: {
    label: "H002 · AC / Motor / Light Home",
    people: ["father", "mother"],
    devices: [
      { id: "bedroom_ac", label: "Bedroom AC", type: "ac", room: "bedroom" },
      {
        id: "living_room_light",
        label: "Light",
        type: "light",
        room: "living_room",
      },
      { id: "living_room_ac", label: "AC", type: "ac", room: "living_room" },
      {
        id: "garden_light",
        label: "Garden Light",
        type: "light",
        room: "garden",
      },
      { id: "porch_light", label: "Porch Light", type: "light", room: "porch" },
      {
        id: "borewell_motor",
        label: "Borewell Motor",
        type: "motor",
        room: "utility",
      },
      { id: "front_door", label: "Front Door", type: "door", room: "entrance" },
    ],
  },
  H004: {
    label: "H004 · Context-Aware Home ✨",
    people: ["father", "mother"],
    devices: [
      { id: "living_room_ac", label: "Living AC", type: "ac", room: "living_room" },
      { id: "bedroom_ac", label: "Bedroom AC", type: "ac", room: "bedroom" },
      { id: "porch_light", label: "Porch Light", type: "light", room: "porch" },
      { id: "water_motor", label: "Water Motor", type: "motor", room: "utility" },
      { id: "mother_presence", label: "Mother", type: "presence", room: "entrance" },
    ],
  },
  H003: {
    label: "H003 · Indian-Context Care Home",
    people: ["grandpa", "grandma", "father", "mother", "son", "ananya", "maid"],
    devices: [
      // Elderly care
      { id: "grandpa_activity", label: "Grandpa Activity", type: "activity", room: "grandpa_room" },
      { id: "grandma_medicine", label: "Grandma Medicine", type: "medicine", room: "grandma_room" },
      // Morning pooja
      { id: "pooja_lamp", label: "Pooja Lamp", type: "light", room: "pooja_room" },
      { id: "temple_bell", label: "Temple Bell", type: "bell", room: "pooja_room" },
      { id: "bhajan_speaker", label: "Bhajan Speaker", type: "speaker", room: "pooja_room" },
      // Son departure (ordinary appliances)
      { id: "son_room_fan", label: "Fan", type: "fan", room: "son_room" },
      { id: "son_room_light", label: "Light", type: "light", room: "son_room" },
      // Entrance: door + people/security/delivery sensors
      { id: "main_door", label: "Main Door", type: "door", room: "entrance" },
      { id: "maid_presence", label: "Helper", type: "presence", room: "entrance" },
      { id: "ananya_presence", label: "Ananya", type: "presence", room: "entrance" },
      { id: "milk_delivery", label: "Milk Delivery", type: "presence", room: "entrance" },
      // Kitchen: chai + dinner + chore
      { id: "chai_kettle", label: "Chai Kettle", type: "kettle", room: "kitchen" },
      { id: "kitchen_light", label: "Kitchen Light", type: "light", room: "kitchen" },
      { id: "kitchen_gas_stove", label: "Gas Stove", type: "stove", room: "kitchen" },
      { id: "water_can_refill", label: "Water Can", type: "can", room: "kitchen" },
      // Terrace
      { id: "terrace_clothesline", label: "Clothesline", type: "clothesline", room: "terrace" },
      // Porch security light
      { id: "porch_light", label: "Porch Light", type: "light", room: "porch" },
      // Utility: overhead-tank motor + inverter
      { id: "water_motor", label: "Water Motor", type: "motor", room: "store_room" },
      { id: "inverter", label: "Inverter", type: "motor_inverter", room: "store_room" },
    ],
  },
};

// Which rooms to render for a given household (only rooms that hold a device).
export function roomsForHousehold(householdId) {
  const used = new Set(HOUSEHOLDS[householdId].devices.map((d) => d.room));
  return Object.entries(ROOMS)
    .filter(([key]) => used.has(key))
    .map(([key, room]) => ({ key, ...room }));
}
