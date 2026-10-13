/**
 * desktop/plugin.js — native desktop control pane for hermes-iroh-gateway.
 *
 * Unified-package half: this file gets copied by the Electron app into
 * desktop-plugins/hermes-iroh-gateway/ at runtime (same hot-reload pipeline
 * as a standalone disk plugin). It talks to this package's OWN backend
 * namespace (dashboard/plugin_api.py) via ctx.rest / ctx.socket, scoped to
 * /api/plugins/hermes-iroh-gateway/ by construction.
 *
 * Opt-in: defaultEnabled is left at its default (true) here, but remember
 * the Python backend only actually imports once "hermes-iroh-gateway" is
 * also in `plugins.enabled` in config.yaml — enabling this pane in
 * Settings -> Plugins alone does not import Python.
 *
 * Only @hermes/plugin-sdk, react, and react/jsx-runtime are importable.
 */
import {
  atom,
  Badge,
  Button,
  cn,
  CopyButton,
  EmptyState,
  haptic,
  host,
  queryClient,
  ScrollArea,
  Separator,
  StatusDot,
  Textarea,
  Tip,
  useMutation,
  useQuery,
  useValue
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'hermes-iroh-gateway'
const STATUS_KEY = [ID, 'status']
const BLOBS_KEY = [ID, 'blobs']

function useGatewayStatus(ctx) {
  return useQuery({
    queryKey: STATUS_KEY,
    queryFn: () => ctx.rest('/status'),
    refetchInterval: 3000
  })
}

function useBlobs(ctx, running) {
  return useQuery({
    queryKey: BLOBS_KEY,
    queryFn: () => ctx.rest('/blobs'),
    enabled: !!running,
    refetchInterval: 5000
  })
}

function StatusHeader({ ctx, status, isLoading }) {
  const running = !!status?.running

  const startMutation = useMutation({
    mutationFn: () => ctx.rest('/start', { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: STATUS_KEY })
      host.notify({ kind: 'success', message: 'iroh gateway starting…' })
    },
    onError: err => host.notify({ kind: 'error', message: `Start failed: ${err?.message || err}` })
  })

  const stopMutation = useMutation({
    mutationFn: () => ctx.rest('/stop', { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: STATUS_KEY })
      host.notify({ kind: 'info', message: 'iroh gateway stopped' })
    }
  })

  return jsxs('div', {
    className: 'flex items-center justify-between gap-2',
    children: [
      jsxs('div', {
        className: 'flex items-center gap-2 text-sm',
        children: [
          jsx(StatusDot, { status: running ? 'success' : 'neutral' }),
          jsx('span', { className: 'font-medium', children: running ? 'Running' : 'Stopped' }),
          isLoading && jsx('span', { className: 'text-(--ui-text-quaternary) text-xs', children: '…' })
        ]
      }),
      jsx(Button, {
        size: 'sm',
        variant: running ? 'outline' : 'default',
        disabled: startMutation.isPending || stopMutation.isPending,
        onClick: () => {
          haptic('tap')
          running ? stopMutation.mutate() : startMutation.mutate()
        },
        children: running ? 'Stop' : 'Start'
      })
    ]
  })
}

function GatewayInfo({ status }) {
  if (!status?.running) {
    return jsx('div', {
      className: 'text-xs text-(--ui-text-tertiary)',
      children: status?.last_error ? `Last error: ${status.last_error}` : 'Gateway is not running.'
    })
  }
  const row = (label, value, copyable) =>
    jsxs('div', {
      className: 'flex items-center justify-between gap-2 text-xs py-0.5',
      children: [
        jsx('span', { className: 'text-(--ui-text-tertiary)', children: label }),
        jsxs('div', {
          className: 'flex items-center gap-1 font-mono truncate max-w-[160px]',
          children: [
            jsx('span', { className: 'truncate', title: String(value), children: String(value) }),
            copyable && jsx(CopyButton, { value: String(value) })
          ]
        })
      ]
    })
  return jsxs('div', {
    className: 'flex flex-col gap-0.5',
    children: [
      row('Gateway URL', status.gateway_url, true),
      row('Node ID', status.node_id, true),
      row('Blobs', status.blob_count, false),
      row('Data dir', status.data_dir, true)
    ]
  })
}

// Module-scope atom: the SDK has no useState/useRef, only atom/computed for
// plugin-local state, so a per-render closure variable would get wiped on
// every re-render (the mutation's isPending flips trigger exactly that) —
// this is the "read state imperatively, never from a render closure"
// pitfall called out in the desktop-plugin docs. One atom is fine here
// since only one gateway pane instance ever exists.
const draftText = atom('')

function PutFormInner({ ctx, running }) {
  const draft = useValue(draftText)

  const putMutation = useMutation({
    mutationFn: text => ctx.rest('/blobs/text', { method: 'POST', body: { text } }),
    onSuccess: result => {
      queryClient.invalidateQueries({ queryKey: BLOBS_KEY })
      draftText.set('')
      host.notify({ kind: 'success', message: `Stored blob ${result.hash.slice(0, 12)}…` })
    },
    onError: err => host.notify({ kind: 'error', message: `Put failed: ${err?.message || err}` })
  })

  return jsxs('div', {
    className: 'flex flex-col gap-1.5',
    children: [
      jsx(Textarea, {
        placeholder: running ? 'Paste text to store as a blob…' : 'Start the gateway first',
        disabled: !running,
        rows: 2,
        className: 'text-xs',
        value: draft,
        onChange: e => draftText.set(e.target.value)
      }),
      jsx(Button, {
        size: 'sm',
        variant: 'outline',
        disabled: !running || putMutation.isPending,
        onClick: () => {
          haptic('tap')
          if (draftText.get().trim()) putMutation.mutate(draftText.get())
        },
        children: 'Add blob'
      })
    ]
  })
}

function BlobList({ ctx, status }) {
  const { data: blobs, isLoading } = useBlobs(ctx, status?.running)

  if (!status?.running) return null
  if (isLoading) return jsx('div', { className: 'text-xs text-(--ui-text-quaternary)', children: 'Loading…' })
  if (!blobs?.length) return jsx(EmptyState, { title: 'No blobs yet', description: 'Add one above.' })

  return jsx(ScrollArea, {
    className: 'max-h-40',
    children: jsx('div', {
      className: 'flex flex-col gap-1',
      children: blobs.map(b =>
        jsxs('div', {
          key: b.hash,
          className: 'flex items-center justify-between gap-2 text-[0.6875rem] font-mono',
          children: [
            jsx('span', { className: 'truncate max-w-[140px]', title: b.hash, children: b.hash }),
            jsxs('div', {
              className: 'flex items-center gap-1 text-(--ui-text-quaternary)',
              children: [
                jsx(Badge, { variant: 'outline', children: `${b.size ?? '?'}B` }),
                jsx(CopyButton, { value: `${status.gateway_url}/blobs/${b.hash}` })
              ]
            })
          ]
        })
      )
    })
  })
}

function IrohGatewayPane({ ctx }) {
  const { data: status, isLoading } = useGatewayStatus(ctx)

  return jsxs('div', {
    className: 'flex h-full flex-col gap-3 p-3 text-sm overflow-y-auto',
    children: [
      jsx(StatusHeader, { ctx, status, isLoading }),
      jsx(Separator, {}),
      jsx(GatewayInfo, { status }),
      jsx(Separator, {}),
      jsx(PutFormInner, { ctx, running: !!status?.running }),
      jsx(Separator, {}),
      jsx(BlobList, { ctx, status })
    ]
  })
}

function GatewayChip({ ctx }) {
  const { data: status } = useGatewayStatus(ctx)
  const running = !!status?.running

  return jsx(Tip, {
    label: running ? `iroh gateway: ${status.gateway_url}` : 'iroh gateway: stopped',
    children: jsxs('button', {
      type: 'button',
      className: cn(
        'inline-flex h-full items-center gap-1 px-1.5 text-[0.6875rem] transition-colors',
        'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
      ),
      onClick: () => {
        haptic('tap')
        host.navigate?.('/') // no dedicated route; pane lives in the layout
      },
      children: [jsx(StatusDot, { status: running ? 'success' : 'neutral' }), 'iroh']
    })
  })
}

export default {
  id: ID,
  name: 'Iroh Gateway',
  register(ctx) {
    ctx.register({
      id: 'pane',
      area: 'panes',
      title: 'iroh gateway',
      data: { placement: 'right', width: '280px' },
      render: () => jsx(IrohGatewayPane, { ctx })
    })

    ctx.register({
      id: 'chip',
      area: 'statusBar.right',
      order: 140,
      render: () => jsx(GatewayChip, { ctx })
    })
  }
}
