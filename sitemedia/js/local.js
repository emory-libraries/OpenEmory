/* make console.log not an error even if console is not available */
if (!window.console) console = {};
console.log = console.log || function(){};
console.warn = console.warn || function(){};
console.error = console.error || function(){};
console.info = console.info || function(){};


String.prototype.ucfirst = function() {
    // method to uppercase the first letter in a string
    return this.substr(0, 1).toUpperCase() + this.substr(1);
}
