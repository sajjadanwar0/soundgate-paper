use pyo3::basic::CompareOp;
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyAny;
use std::io::{BufRead, BufReader, Write};
use std::net::TcpStream;
use std::sync::Mutex;

use crate::{Admission, Effect, Gate as CoreGate};

#[allow(dead_code)]
#[path = "hmac.rs"]
mod hmac;

fn verdict_str(a: &Admission) -> &'static str {
    match a {
        Admission::Release => "release",
        Admission::HeldForApproval => "held_for_approval",
        Admission::RefusedCancelled => "refused_cancelled",
        Admission::RefusedDuplicate => "refused_duplicate",
        Admission::RefusedRejected => "refused_rejected",
    }
}

#[pyclass(frozen, module = "soundgate")]
#[derive(Clone)]
pub struct Verdict {
    #[pyo3(get)]
    kind: String,
}

#[pymethods]
impl Verdict {
    #[getter]
    fn released(&self) -> bool {
        self.kind == "release"
    }

    #[getter]
    fn held(&self) -> bool {
        self.kind == "held_for_approval"
    }

    #[getter]
    fn refused(&self) -> bool {
        self.kind.starts_with("refused_")
    }

    fn __str__(&self) -> String {
        self.kind.clone()
    }

    fn __repr__(&self) -> String {
        format!("Verdict('{}')", self.kind)
    }

    fn __richcmp__(&self, other: &Bound<'_, PyAny>, op: CompareOp) -> bool {
        let eq = if let Ok(s) = other.extract::<String>() {
            self.kind == s
        } else if let Ok(v) = other.extract::<Verdict>() {
            self.kind == v.kind
        } else {
            false
        };

        match op {
            CompareOp::Eq => eq,
            CompareOp::Ne => !eq,
            _ => false,
        }
    }
}

impl Verdict {
    fn of(a: &Admission) -> Verdict {
        Verdict {
            kind: verdict_str(a).to_string(),
        }
    }
    fn from_str(s: &str) -> Verdict {
        Verdict { kind: s.to_string() }
    }
}

#[pyclass(module = "soundgate")]
pub struct Gate {
    inner: Mutex<CoreGate>,
}

#[pymethods]
impl Gate {
    #[new]
    fn new() -> Self {
        Gate {
            inner: Mutex::new(CoreGate::new()),
        }
    }

    #[pyo3(signature = (run_id, effect_key, needs_approval = false))]
    fn submit(&self, run_id: String, effect_key: String, needs_approval: bool) -> Verdict {
        let mut g = self.inner.lock().unwrap();
        Verdict::of(&g.submit(Effect {
            run_id,
            effect_key,
            needs_approval,
        }))
    }

    fn decide(&self, run_id: &str, effect_key: &str, approved: bool) -> Verdict {
        let mut g = self.inner.lock().unwrap();
        Verdict::of(&g.decide(run_id, effect_key, approved))
    }

    fn cancel(&self, run_id: &str) {
        self.inner.lock().unwrap().cancel(run_id);
    }

    fn close_run(&self, run_id: &str) {
        self.inner.lock().unwrap().close_run(run_id);
    }

    fn is_cancelled(&self, run_id: &str) -> bool {
        self.inner.lock().unwrap().is_cancelled(run_id)
    }
    fn is_closed(&self, run_id: &str) -> bool {
        self.inner.lock().unwrap().is_closed(run_id)
    }
    fn pending_count(&self) -> usize {
        self.inner.lock().unwrap().pending_count()
    }
    fn state_len(&self) -> usize {
        self.inner.lock().unwrap().state_len()
    }
}

#[pyclass(module = "soundgate")]
pub struct GateClient {
    conn: Mutex<BufReader<TcpStream>>,
    secret: Option<Vec<u8>>,
}

impl GateClient {
    fn roundtrip(&self, py: Python<'_>, line: String) -> PyResult<Verdict> {
        py.allow_threads(|| {
            let mut c = self.conn.lock().unwrap();

            c.get_mut()
                .write_all(line.as_bytes())
                .and_then(|_| c.get_mut().write_all(b"\n"))
                .and_then(|_| c.get_mut().flush())
                .map_err(|e| PyRuntimeError::new_err(format!("gate write failed: {e}")))?;

            let mut resp = String::new();

            let n = c
                .read_line(&mut resp)
                .map_err(|e| PyRuntimeError::new_err(format!("gate read failed: {e}")))?;

            if n == 0 {
                return Err(PyRuntimeError::new_err("gate closed the connection"));
            }

            let v: serde_json::Value = serde_json::from_str(resp.trim())
                .map_err(|e| PyRuntimeError::new_err(format!("bad gate reply {resp:?}: {e}")))?;
            match v.get("verdict").and_then(|x| x.as_str()) {
                Some("error") => Err(PyRuntimeError::new_err(format!(
                    "gate error: {}",
                    v.get("message").and_then(|m| m.as_str()).unwrap_or("?")
                ))),
                Some(s) => Ok(Verdict::from_str(s)),
                None => Err(PyRuntimeError::new_err(format!(
                    "gate reply missing verdict: {resp:?}"
                ))),
            }
        })
    }
}

#[pymethods]
impl GateClient {
    #[new]
    #[pyo3(signature = (addr = "127.0.0.1:8796", secret = None))]
    fn new(addr: &str, secret: Option<Vec<u8>>) -> PyResult<Self> {
        let stream = TcpStream::connect(addr)
            .map_err(|e| PyRuntimeError::new_err(format!("connect {addr} failed: {e}")))?;
        stream.set_nodelay(true).ok();
        Ok(GateClient {
            conn: Mutex::new(BufReader::new(stream)),
            secret,
        })
    }

    #[pyo3(signature = (run_id, effect_key, needs_approval = false))]
    fn submit(
        &self,
        py: Python<'_>,
        run_id: &str,
        effect_key: &str,
        needs_approval: bool,
    ) -> PyResult<Verdict> {
        let req = serde_json::json!({
            "op": "submit", "run_id": run_id,
            "effect_key": effect_key, "needs_approval": needs_approval,
        });
        self.roundtrip(py, req.to_string())
    }

    fn decide(
        &self,
        py: Python<'_>,
        run_id: &str,
        effect_key: &str,
        approved: bool,
    ) -> PyResult<Verdict> {
        let mut req = serde_json::json!({
            "op": "decide", "run_id": run_id,
            "effect_key": effect_key, "approved": approved,
        });
        if let Some(sec) = &self.secret {
            let tag = hmac::decision_tag(sec, run_id, effect_key, approved);
            req["mac"] = serde_json::Value::String(tag);
        }
        self.roundtrip(py, req.to_string())
    }

    fn cancel(&self, py: Python<'_>, run_id: &str) -> PyResult<Verdict> {
        let req = serde_json::json!({ "op": "cancel", "run_id": run_id });
        self.roundtrip(py, req.to_string())
    }

    fn ping(&self, py: Python<'_>) -> PyResult<Verdict> {
        self.roundtrip(py, "{\"op\":\"ping\"}".to_string())
    }
}

#[pyfunction]
fn decision_tag(secret: Vec<u8>, run_id: &str, effect_key: &str, approved: bool) -> String {
    hmac::decision_tag(&secret, run_id, effect_key, approved)
}

#[pymodule]
fn soundgate(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Verdict>()?;
    m.add_class::<Gate>()?;
    m.add_class::<GateClient>()?;
    m.add_function(wrap_pyfunction!(decision_tag, m)?)?;
    Ok(())
}