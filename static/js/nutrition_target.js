document.addEventListener("DOMContentLoaded", () => {
  const el = document.getElementById("macrosChart");
  const dataEl = document.getElementById("macros-data");

  if (!el || !dataEl) return;

  try {
    const macros = JSON.parse(dataEl.textContent);

    new Chart(el, {
      type: "doughnut",
      data: {
        labels: ["Protein (g)", "Carbs (g)", "Fat (g)"],
        datasets: [{
          data: [macros.protein, macros.carbs, macros.fat],
          backgroundColor: ["#4e79a7", "#f28e2b", "#e15759"]
        }]
      },
      options: {
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.label}: ${ctx.parsed} g`
            }
          }
        },
        cutout: "60%"
      }
    });
  } catch (err) {
    console.error("Failed to parse macros data", err);
  }
});
