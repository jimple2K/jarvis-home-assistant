import React from 'react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('[jarvis] render error:', error, info);
  }

  handleReload = () => {
    window.location.reload();
  };

  handleReset = () => {
    this.setState({ error: null });
  };

  render() {
    if (!this.state.error) return this.props.children;
    const stack = String(this.state.error?.stack || this.state.error?.message || this.state.error);
    return (
      <div className="error-boundary" role="alert">
        <div className="error-boundary-card">
          <h2>Something went wrong.</h2>
          <p>
            Jarvis hit a render error. The server is still running — you can
            try resetting the UI or reload the window.
          </p>
          <pre>{stack}</pre>
          <div className="srow">
            <button className="sbtn p" onClick={this.handleReload}>Reload</button>
            <button className="sbtn" onClick={this.handleReset}>Try Again</button>
          </div>
        </div>
      </div>
    );
  }
}
