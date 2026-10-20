import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Field } from '../components/ui'

function useRedirect() {
  const loc = useLocation()
  return (loc.state as { from?: string } | null)?.from ?? '/discover'
}

export function Login() {
  const { login, user } = useAuth()
  const nav = useNavigate()
  const dest = useRedirect()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  if (user) return <Navigate to={dest} replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const v: Record<string, string> = {}
    if (!/^\S+@\S+\.\S+$/.test(email)) v.email = 'Enter a valid email address.'
    if (!password) v.password = 'Enter your password.'
    setErr(v)
    if (Object.keys(v).length) return
    setBusy(true)
    try {
      await login(email, password)
      nav(dest, { replace: true })
    } catch (x) {
      setErr({ form: x instanceof ApiError ? x.message : 'Sign in failed.' })
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="mx-auto max-w-md rounded-lg border border-rule bg-card p-7">
      <h1 className="text-3xl font-semibold">Welcome back</h1>
      <form onSubmit={submit} noValidate className="mt-6 space-y-4">
        {err.form && (
          <p role="alert" className="rounded bg-[#f8e9e6] px-3 py-2 text-sm text-alert">
            {err.form}
          </p>
        )}
        <Field label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} error={err.email} />
        <Field label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} error={err.password} />
        <button className="btn w-full" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <p className="mt-5 text-sm text-ink-soft">
        New here?{' '}
        <Link to="/register" className="font-semibold text-forest hover:underline">
          Create an account
        </Link>
      </p>
    </div>
  )
}

export function Register() {
  const { register, user } = useAuth()
  const [justRegistered, setJustRegistered] = useState(false)
  const [f, setF] = useState({ name: '', email: '', password: '' })
  const [err, setErr] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  if (user) return <Navigate to={justRegistered ? '/settings' : '/discover'} replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const v: Record<string, string> = {}
    if (!f.name.trim()) v.name = 'Tell us what to call you.'
    if (!/^\S+@\S+\.\S+$/.test(f.email)) v.email = 'Enter a valid email address.'
    if (f.password.length < 10) v.password = 'Use at least 10 characters.'
    setErr(v)
    if (Object.keys(v).length) return
    setBusy(true)
    try {
      setJustRegistered(true)
      await register(f.email, f.password, f.name.trim())
    } catch (x) {
      setJustRegistered(false)
      if (x instanceof ApiError) {
        const fe = x.fieldErrors()
        const taken = x.code === 'email_taken'
        setErr({
          form: Object.keys(fe).length || taken ? '' : x.message,
          email: fe.email ?? (taken ? x.message : ''),
          password: fe.password ?? '',
          name: fe.display_name ?? '',
        })
      } else setErr({ form: 'Registration failed.' })
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="mx-auto max-w-md rounded-lg border border-rule bg-card p-7">
      <h1 className="text-3xl font-semibold">Start your shelf</h1>
      <form onSubmit={submit} noValidate className="mt-6 space-y-4">
        {err.form && (
          <p role="alert" className="rounded bg-[#f8e9e6] px-3 py-2 text-sm text-alert">
            {err.form}
          </p>
        )}
        <Field label="Display name" autoComplete="nickname" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} error={err.name} />
        <Field label="Email" type="email" autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} error={err.email} />
        <Field label="Password" type="password" autoComplete="new-password" hint="At least 10 characters." value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} error={err.password} />
        <button className="btn w-full" disabled={busy}>
          {busy ? 'Creating account…' : 'Create account'}
        </button>
      </form>
      <p className="mt-5 text-sm text-ink-soft">
        Already registered?{' '}
        <Link to="/login" className="font-semibold text-forest hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  )
}
